import os
import time
import shutil
import shared
import Agent
import NetworkAudit.sharkutils as sharkutils
from multisig_lspnr import multisig

#for brevity
def g(x,y):
    return shared.config.get(x,y)
    
class UserAgent(Agent.Agent):
    #list of available logins to any UserAgent instance, so class level
    
    
    def __init__(self,basedir,btcaddress,bankinfo,currency):
        
        #load our transactions
        super(UserAgent,self).__init__(basedir=basedir, btcadd=btcaddress,currency=currency)
        
        self.escrows=[]
        #all user agents (not escrows) must provide basic bank info
        #TODO: put validation code that info has correct form
        self.bankInfo=bankinfo
        
        #The active escrow is not yet defined.
        self.activeEscrow = None
        
        #store the location used for the NSS key log file
        self.keyFile=g("Directories","ssl_keylog_file")
        
        #the running stcppipe which we own
        self.stcppipe_proc=None
        
        #the running ssh or plink process which we own
        self.ssh_proc = None
    

    #calling this function for a particular transaction means that the user
    #has decided to carry out the required next action.
    def takeAppropriateActions(self, txID):
        tx = self.getTxByID(txID)
        
        #tx.state must be in one of the 'pending' states:
        if tx.state not in [300,501,502,700,701,702,706,800]:
            return
        
        if tx.state in [300,501]:
            self.doBankingSession(tx)
            
        elif tx.state==700 or (tx.getRole(self.uniqID())=='buyer' and tx.state==702) \
            or (tx.getRole(self.uniqID())=='seller' and tx.state==701):
            my_ssl_data = ','.join(self.getHashList(tx))
            if tx.getRole(self.uniqID()) == 'buyer':
                #need to send the magic hashes telling the escrow which other hashes
                #to ignore in the comparison
                my_ssl_data += '^'+','.join(self.getMagicHashList(tx))
                
            self.activeEscrow.sendMessages(messages=\
            {'x':'SSL_DATA_SEND:'+my_ssl_data},transaction=tx,rs=703)
            
        elif tx.state==800 and tx.getRole(self.uniqID())=='buyer':
            #TODO: this action naturally fits a GUI; for now just get
            #user to choose one or more key numbers
            keydir = os.path.join(g("Directories","agent_base_dir"),\
            '_'.join([tx.getRole(self.uniqID()),tx.uniqID(),"banksession"]),"keys")
            print ("You have chosen to send ssl keys to the escrow."
            "Do this carefully. Check the folder: ", keydir ," and "
            "decide which key number or numbers to send by looking at the "
            "corresponding html in the html directory, then enter those "
            "numbers here one by one at the prompt. When finished, type 0.")
            #get a listing of all valid key files
            all_keys = os.listdir(keydir)
            requested_keys=[]
            while True:
                choice = shared.get_validated_input("Enter a number (0 to quit)",int)
                if choice == 0:
                    if not any(requested_keys):
                        print "Error, you must select at least one key."
                    else:
                        print "Keys will now be sent to escrow."
                        break
                else:
                    if str(choice)+'.key' not in all_keys:
                        print "That number does not correspond to an existing \
                            key, please try again."
                    else:
                        requested_keys.append(os.path.join(keydir,str(choice)+'.key'))
                        
            self.sendSSLKeys(tx,requested_keys)
            
        else:
            shared.debug(0,["Unexpected request to perform action on",\
                            "a transaction that doesn't need anything done."])
    
    #must be called with a list of filenames that the user has chosen,
    #each containing a particular ssl key (in the "keys" subdirectory under
    #the transaction directory)
    def sendSSLKeys(self,transaction,keyfiles):
        if (transaction.getRole(self.uniqID()) != 'buyer'):
            shared.debug(0,["Error, get keys was called for a transaction",\
                            "where we're not the buyer!"])
        keys = []
        for kf in keyfiles:
            with open(kf) as f:
                shared.debug(0,["Trying to open a keyfile:",kf])
                keys.append(f.readline())
        shared.debug(0,["Set keys to:",keys])
        self.activeEscrow.sendMessages({'x':'DISPUTE_L2_SEND_SSL_KEYS:'+\
                                ','.join(keys)},transaction=transaction,rs=801)
        
    #to be called after escrow accessor is initialised
    #and transaction list is synchronised.
    #return value is a dict of transaction IDs with actionable items
    def processExistingTransactions(self):
        #any transaction in one of these states means something 
        #needs to be done. See AppLayer/TransactionStateMap.txt
        actionables = {}
        need_to_process = [300,500,501,502,700,701,702,800]
        for tx in self.transactions:
            if tx.state not in need_to_process:
                continue
            if tx.state in [300,501,500]:
                if tx.getRole(self.uniqID())=='buyer':
                    actionables[tx.uniqID()]='Transaction is ready. Please \
                        coordinate with seller to perform internet banking'
                else:
                    actionables[tx.uniqID()]='Transaction is ready. Please \
                    communicate with buyer and ensure squid is running so that\
                        banking session can be performed.'
            elif tx.state==700 or (tx.state==701 and tx.getRole(self.uniqID())=='seller') \
                or (tx.state==702 and tx.getRole(self.uniqID())=='buyer'):
                actionables[tx.uniqID()]='Transaction is in dispute. Please \
                    send ssl data.'
            elif tx.state == 800 and tx.getRole(self.uniqID())=='buyer':
                actionables[tx.uniqID()]='Transaction has been escalated to \
                    human escrow adjudication, since all ssl was consistent. \
                    Please check which html pages you want to expose to escrow \
                    and then send the appropriate ssl key(s) to the escrow.'
                
        return actionables
    
    def startBankingSession(self,transaction):
        role = transaction.getRole(self.uniqID())
        if role=='invalid':
            shared.debug(0,["Trying to start a banking session but we're not"
                            "buyer or seller for the transaction!"])
            return False
        
        #wipe clean the keylog file
        #remove pre-existing ssl key file so we only load the keys for this run
        #TODO: make sure the user has set the ENV variable - pretty disastrous
        #otherwise!
        if role=='buyer':
            shared.silentremove(self.keyFile)
        
        #create local directories to store this banking session
        #format of name is: role_txid_'banksession'
        #TODO consider how banking sessions may be first class objects;
        #may need more than one per tx
        runID='_'.join([role,transaction.uniqID(),'banksession'])
        d = shared.makedir([g("Directories",'agent_base_dir'),runID])
        #make the directories for the stcp logs
        new_stcp_dir=shared.makedir([d,'stcplog'])
        
        shared.debug(0,["starting banking session as ",role,"\n"])
        
        #notice that the calls for buyer and seller are very similar
        #but the duplication is safer as there are small, easy to miss differences!
        if role == 'buyer':
            self.ssh_proc = shared.local_command([g("Exepaths","sshpass_exepath"), \
g("Agent","escrow_ssh_user") +'@'+g("Escrow","escrow_host"),'-P', \
g("Escrow","escrow_ssh_port"), '-pw', g("Agent","escrow_ssh_pass"),'-N','-L', \
g("Agent","agent_stcp_port")+':127.0.0.1:'+g("Escrow","escrow_input_port")],\
    bg=True)
            
            self.stcppipe_proc = shared.local_command([g("Exepaths","stcppipe_exepath"),'-d',\
            new_stcp_dir,'-b','127.0.0.1',g("Agent","agent_stcp_port"),\
            g("Agent","agent_input_port")],bg=True)
            
        else: 
            self.ssh_proc = shared.local_command([g("Exepaths","sshpass_exepath"), \
g("Agent","escrow_ssh_user")+'@'+g("Escrow","escrow_host"),'-P', \
g("Escrow","escrow_ssh_port"), '-pw', g("Agent","escrow_ssh_pass"),'-N','-R',\
g("Escrow","escrow_host")+':'+g("Escrow","escrow_stcp_port")+':127.0.0.1:'\
+g("Agent","agent_input_port")],bg=True)
            
            self.stcppipe_proc = shared.local_command([g("Exepaths","stcppipe_exepath"),'-d',\
            new_stcp_dir,'-b','127.0.0.1',g("Agent","agent_stcp_port"),\
            g("Agent","agent_input_port")],bg=True)
         
         #we must return to confirm success in startup of net arch
        return True 
      
    #the argument rspns indicates whether or not the banking session 
    #was successful
    def endBankingSession(self,transaction,rspns):
        
        #tear down network connections
        shared.kill_processes([self.ssh_proc,self.stcppipe_proc])
        
        role = transaction.getRole(self.uniqID())
            
        if role=='buyer' and rspns=='y':
            #copy the premaster secrets file into the testing directory
            #so that it can be decrypted at a later stage by the buyer
            runID='_'.join([role,transaction.uniqID(),'banksession'])
            key_file_name = os.path.join(g("Directories",'agent_base_dir'),\
                                         runID,runID+'.keys')
            shutil.copy2(self.keyFile,key_file_name)
            transaction.keyFile = key_file_name
            
            #TODO: consider how in the transaction model, the keyFile
            #info is/is not propagated to the escrow, who after all must
            #be the arbiter of the correct state of the transaction object
            
            #3 Oct 2013: now we want to provide the buyer with the ability to 
            #(a) read the html traced and (b) to separate it per ssl key for
            #selective upload to escrow in case of dispute
            #note: this will work assuming the user has chosen to clear
            #the ssl cache after each click, or some automated version of
            #that has been implemented in the plugin
            #(first step is to create a merged trace file:)
            stcpdir=os.path.join(g("Directories",'agent_base_dir'),runID,'stcplog')
            merged_trace = os.path.join(stcpdir,'merged.pcap')
            sharkutils.mergecap(merged_trace,stcpdir,dir=True)
            html = sharkutils.get_html_key_by_key(merged_trace,transaction.keyFile)
            d = os.path.join(os.path.dirname(transaction.keyFile),'html')
            if not os.path.exists(d): os.makedirs(d)
            for k,v in html.iteritems():
                if not v:
                    continue
                for i,h in enumerate(v):
                    #file format: key number_htmlindex.html, all
                    #stored in a subdirectory called 'html'.
                    f = os.path.join(d,k+'_'+str(i)+'.html')
                    fh = open(f,'w')
                    print>>fh, h
                    fh.close()
            #in GUI(?) we can now give user ability to select html
            #to send, in case there's a dispute, and he'll only send the 
            #key(s) that correspond to that html
            
        new_state = 502 if rspns=='y' else 501
        self.transactionUpdate(tx=transaction,new_state=new_state)
        
                
    #this method is at useragent level only as it's only for buyers
    #see details in sharkutils.get_magic_hashes
    def getMagicHashList(self, tx):
        if (tx.getRole(self.uniqID()) != 'buyer'):
            shared.debug(0,["Error! You cannot send the magic hashes unless"\
                            "you\'re the buyer!"])
            exit(1)
            
        txdir = os.path.join(g("Directories","agent_base_dir"),\
                        '_'.join(["buyer",tx.uniqID(),"banksession"]))
        stcpdir = os.path.join(txdir,"stcplog")
        kf = os.path.join(txdir,'_'.join(['buyer',tx.uniqID(),'banksession.keys']))
        shared.debug(0,["Trying to find any magic hashes located in:",\
                    stcpdir,"using ssl decryption key:",kf])
        return sharkutils.get_magic_hashes(stcpdir,kf,\
                                        port=g("Agent","agent_stcp_port"))
        
    def doBankingSession(self,tx):
        rspns=''
        role = tx.getRole(self.uniqID())
        if role =='buyer':
            self.activeEscrow.requestBankSessionStart(tx)
    
        #wait for response - same for both parties at least in this script.
        if not self.activeEscrow.negotiateBankSession(tx):
            shared.debug(0,["We failed to initialise the banking session"\
                            "properly, unfortunately. Returning to menu."])
            self.endBankingSession(tx,'n')
            return False
    
        #if we reached here as seller it means we promise that squid is running.
        #if we reached here as buyer it means we promise to be ready to start banking.
    
        #here we set up the pipes for the internet traffic, as long as everything
        #is in order
        if not self.startBankingSession(tx): 
            shared.debug(0,["Could not start banking session for transaction",\
                tx.uniqID(),"because this transaction does not belong to you."])
            exit(1)
    
        if role=='buyer':
            print ("When firefox starts, please perform internet banking."
            "If you can't connect, please close the browser."
            "If you can connect, then when you have finished your internet"
            "banking, please close firefox.")
            time.sleep(5)
            shared.local_command([g("Exepaths","firefox_exepath")],bg=True)
        
            #TODO: need to set things using a plugin
            #TODO: insert test session; escrow can check if it can 
            #receive valid SSL using a test case
            #something to account for the case where the proxy didn't work?
            #TODO: this will need some serious 'refactoring'!
            ffname = os.path.basename(g("Exepaths","firefox_exepath"))
            shared.wait_for_process_death(ffname)
            
            rspns = shared.get_binary_user_input("Did you complete the payment successfully?",\
                                         'y','y','n','n')
            
            #we have finished our banking session. We need to tell the others.
            self.activeEscrow.sendConfirmationBankingSessionEnded(tx,rspns)
            #if we shut down python immediately the connection is dropped 
            #and the message gets dropped! Ouch, what a bug!TODO
            time.sleep(10)
            #TODOput some code to get the confirmation of storage from escrow
            #(and counterparty?) so as to be sure everything was done right
        else:
            shared.debug(0,["Waiting for signal of end of banking session."])
        
            #wait for message telling us the buyer's finished
            rspns = 'y' if self.activeEscrow.waitForBankingSessionEnd(tx) else 'n'
            shared.debug(0,["The banking session is finished."])
    
        #final cleanup - for now only storing the premaster keys
        self.endBankingSession(tx,rspns)
        
    #unused for now
    def findEscrow(self):
        print "finding escrow\n"
        self.escrow = EscrowAgent()
    
    def addEscrow(self,escrow):
        self.escrows.append(escrow)
        return self
    
    def setActiveEscrow(self,escrow):
        if escrow in self.escrows:
            self.activeEscrow = escrow 
        else:
            raise Exception("Attempted to set active an escrow which is not known to this user agent!.\n")
        return self
        
    
