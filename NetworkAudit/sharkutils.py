
#====LIBRARY IMPORTS====
import re
import os
import platform
import ConfigParser
import shared
#for brevity
def g(x,y):
    return shared.config.get(x,y)
import subprocess
import hashlib
import shutil
import itertools
#======================

#====GLOBALS===========
#required to address limit on length of filter string for tshark
MAX_FRAME_FILTER = 500
#======================

#wrapper for running tshark to extract data
#using the syntax -T fields
#output is filtered by a list of frame numbers
#and/or any other filter in Wireshark's -R syntax
def tshark(infile, field='', filter='', frames=[],options=[]):
    tshark_out = ''
    
    if (frames and len(frames)>MAX_FRAME_FILTER):
        #we will need to get our output in chunks to avoid
        #issues with going over the hard limit on filter strings
        #in *shark
        shared.debug(3,["Splitting tshark request into multiple steps"])
        start_window = 0
        while (start_window+MAX_FRAME_FILTER < len(frames)):
            print "starting a tshark run with start_window: " + str(start_window)
            tshark_out += tshark_inner(infile,field=field,filter=filter, \
            frames=frames[start_window:start_window+MAX_FRAME_FILTER],options=options)
            start_window += MAX_FRAME_FILTER

        tshark_out += tshark_inner(infile,field=field,filter=filter, \
            frames=frames[start_window:],options=options)
    else:
        tshark_out += tshark_inner(infile,field=field,filter=filter, \
        frames=frames,options=options)
    #print "Final tshark output: \n" + tshark_out
    return tshark_out   


def tshark_inner(infile, field='', filter='', frames=[],options=[]):
    tshark_exepath =  g("Exepaths","tshark_exepath")
    args = [tshark_exepath,'-r',infile] 
    
    if (frames and not filter): 
        args.extend(['-Y', 'frame.number==' + ' or frame.number=='.join(frames)])
    elif (frames and filter):
        args.extend(['-Y', 'frame.number==' + ' or frame.number=='.join(frames)\
                     +' and '+filter])
    else: #means - not frames
        if (filter):
            args.extend(['-Y',filter])
    
    if (options):
        for option in options:
            if (option):
                args.extend(['-o',option])
                    
    if (field):
        if field=='x':
            args.append('-x')
        else:
            args.extend(['-T','fields','-e',field])
            
    #command line is now built.
    shared.debug(2,args)
    try:
        return subprocess.check_output(args)
    except:
        shared.debug(0,['Error starting tshark'])
        exit(1)
    
    return tshark_out

# wrapper for running editcap; -r is used
#to include rather than remove frames, filter
#is used to generate a list of frame numbers to include
def editcap(infile, outfile, reverse_flag = 0, filter='', frames=[]):
    editcap_exepath =  g("Exepaths","editcap_exepath")
    frame_list=[]
    if reverse_flag:
        args = [editcap_exepath, '-r', infile]
    else:
        args = [editcap_exepath,infile]
    
    if (frames):
        frame_list = frames
    else:
        tshark_out = tshark(infile,field = 'frame.number',filter = filter)
        frame_list = shared.pisp(tshark_out)
    
    shared.debug(3,["Frames are: ", frame_list]) 
    
    #TODO: This won't work if -r flag not used;
    #may need some reconsideration
    if (len(frame_list)>MAX_FRAME_FILTER):
        editcap_inner(args,frame_list,outfile)
    else:
        args.append(outfile)    
        args.extend(frame_list)
        shared.debug(2,["Calling editcap with these arguments: ",args])
        subprocess.check_output(args)
    

def editcap_inner(args,frames,outfile):
        start_window = 0
        filenames = []
       
        while (start_window+MAX_FRAME_FILTER < len(frames)):
            tmpargs = []
            tmpargs.extend(args)
            shared.debug(1,["starting an editcap run with start_window: " \
                        ,str(start_window)])
            filename = outfile+".tmp."+str(start_window)
            filenames.append(filename)
            tmpargs.append(filename)
            tmpargs.extend(frames[start_window:start_window+MAX_FRAME_FILTER])
            #shared.debug(1,["Here is the call to editcap: ", tmpargs])
            shared.debug(2,["Calling editcap with these arguments: ",tmpargs])
            shared.debug(4,subprocess.check_output(tmpargs))
            start_window += MAX_FRAME_FILTER
        
        args.append(outfile+".tmp."+str(start_window))
        args.extend(frames[start_window:])
        shared.debug(2,["Calling editcap with these arguments: ",args])
        shared.debug(4,subprocess.check_output(args))
        #Lastly, need to concatenate and delete all the temporary files
        args = [g("Exepaths","mergecap_exepath"),'-w',outfile]
        args.extend(filenames)
        subprocess.check_output(args)
       
        for filename in filenames:
            os.remove(filename) 
            
       
#generic mergecap caller
#if dir is True, then infiles is treated as a directory name
#and a wildcard match is used to merge all files in that directory
#if dir is False, then infiles must be a list of full paths to cap files
def mergecap(outfile,infiles,dir=False):
    
    outfile = shared.verify_file_creation(outfile, \
                    "mergecap output already exists!",\
                        overwrite=True,prompt=False,remove_in_advance=True)
    args = [g("Exepaths","mergecap_exepath")]
    if (dir):
        args.extend(['-w',outfile, os.path.join(infiles,'*')])
    else:
        args.extend(['-w',outfile])
        args.extend(infiles)
    shared.debug(0,["mergecap call is:",args])
    try:
        return subprocess.check_output(args)
    except:
        shared.debug(0,["Error in mergecap execution, quitting!"])
        exit(1)
            
def get_ssl_hashes_from_ssl_app_data_list(ssl_app_data_list):
    
    ssl_hashes = []
    for s in ssl_app_data_list:
        #get rid of commas and colons
        #(ssl.app_data comma-delimits multiple SSL segments within the same frame)
        s = s.rstrip()
        s = s.replace(',',' ')
        s = s.replace(':',' ')
        
        if s == '':
            shared.debug(2,["Warning: empty ssl app data string passed for hashing!"])
        else:
            ssl_hashes.append(hashlib.md5(bytearray.fromhex(s)).hexdigest()) 
        
    return list(set(ssl_hashes))
    

#this function is only going to extract the hashes of the encrypted SSL data
#which has been reassembled, to avoid possible issues with segmentation
#of data being different between buyer and seller (i.e. try to ignore any
#TCP-and-above issues as they may differ between buyer and seller)
#4 Sep 2013 rewrite to use stcppipe instead of gateway bouncing
#The first argument CAPFILE can take one of two possible forms:
#either the full path of a single pcap file (if captured using dumpcap)
#or a full path to a directory containing a set of acp files collected by stcppipe
#7 Sep 2013 in case of tshark, can set stream to capture only hashes from one stream
def get_all_ssl_hashes_from_capfile(capfile, handshake= False, port= -1, \
                                    stcp_flag=False,stream='',in_options=[]):
    hashes = []
    for options in build_option_list(in_options=in_options):
        if stcp_flag:
            
            #here "capfile" is not actually a file, it's the directory
            #containing all the per-stream captures.
            #(stcppipe logs multiple capfiles, one per stream)
            
            
            #6 Sep 2013: The following is to merge the stcppipe log files into one pcap
            #unfortunately, stcppipe currently does not mark separate stream numbers
            #(all tcp streams have stream index 0) and so the merged file CANNOT
            #be used currently.
            #Update 8 Sep 2013 updated stcppipe called stcppipe_port solves
            #problem by using client port so that merged file now has
            #separate streams. Can still use 'basic' stcppipe, but it will be slower
            #edited 17th Sept - we have abandoned 'non-port' stcppipe.
            shared.debug(1,[\
    "stcppipe_port found; merging all streams from stcppipe for processing.."])
            merged_stcp_file = os.path.join(capfile,"merged.pcap") #TODO: magic string?
            shared.debug(1,["merged stcppipe filename is:",merged_stcp_file])
            mergecap(merged_stcp_file,capfile,dir=True)
            return get_ssl_hashes_from_capfile(capfile=merged_stcp_file,\
                                               port=port,options=options)
                
        else:
            hashes.extend(get_ssl_hashes_from_capfile(capfile=capfile,port=port,\
                                               stream=stream,options=options))
    return hashes
        
        

#remember to handle failure correctly - if this function
#returns null it means that for some reason there was no such ssl data
def get_ssl_hashes_from_capfile(capfile,port=-1,stream='',options=[],frames=[]):
    frames_str=''
    ssl_frames=[]
    #Run tshark to get a list of frames with ssl app data in them
    #EDITED to test escrow
    filterstr = build_filterstr(stream=stream,port=port)
    if (frames):
        ssl_frames=frames
    else:
        try:
            frames_str = tshark(capfile,field='frame.number', \
                            filter= filterstr,options=options)
        except:
            #this could be caused by a corrupt file from stcppipe
            #or by a malformed query string,etc. - but in the former
            #case we should NOT exit, hence this approach
            shared.debug(0,["tshark failed - see stderr for message"])
            shared.debug(0,["return code from tshark: ",frames_str])
            return None
    
        ssl_frames = shared.pisp(frames_str)
        #gracefully handle null result (i.e. blank tshark output):
        ssl_frames = filter(None,ssl_frames)
        if not ssl_frames:
            return None
    
    #Now we definitely have ssl frames in this capture file
    shared.debug(1,['need to process this many frames:', len(ssl_frames)])
    ssl_app_data = tshark(capfile,field='ssl.app_data',frames=ssl_frames,\
                    options=options)
    #ssl.app_data will return all encrypted segments separated by commas
    #but also, lists of segments from different frames will be separated by
    #platform dependent newlines
    ssl_app_data_list = shared.pisp(ssl_app_data.replace(',',shared.PINL))
    #remove any blank OR duplicate entries in the ssl app data list
    ssl_app_data_list = filter(None,list(set(ssl_app_data_list)))
    shared.debug(4,["Full dump of ssl application data:\n",ssl_app_data_list])
    shared.debug(1,["Length of list of ssl segments for file ",capfile," was: " \
    ,len(ssl_app_data_list)])
    
    return get_ssl_hashes_from_ssl_app_data_list(ssl_app_data_list)
    
#===============================================================================
#Functions for debugging purposes
#===============================================================================

#detailed comparison of two captures - finding which frames contain
#ssl hashes which can't be matched in the other capture, and giving a
#stream-by-stream (if appropriate) and frame-by-frame breakdown of the
#hashes found. Beware, this can be SLOW for big files.
def debug_find_mismatch_frames(capfile1, port1, stcp_flag1,capfile2, \
                               port2,stcp_flag2,options=[]):
    data1 = [capfile1,port1,stcp_flag1]
    data2 = [capfile2,port2,stcp_flag2]
    print "stcp flag 1 is: ",stcp_flag1,"\n"
    print "stcp flag 2 is: ",stcp_flag2,"\n"
    #first task is to construct
    #a dict of dicts of dicts of form:
    #{file2:{stream:{frame:hash}}}
    comparison = {}
    
    #instantiation - is this really necessary always for dicts?
    for data in [data1,data2]:
            comparison[data[0]]={}
    
    for data in [data1,data2]:
        if (data[2]): #means stcppipe was used to collect data
            if (g("stcppipe","port")=='1'):
                #merge the files before populating the streams
                shared.debug(1,["stcppipe_port found; merging all streams from \
                stcppipe for processing.."])
                merged_stcp_file = os.path.join(data[0],"merged.pcap")
                shared.debug(1,["merged stcppipe filename is:",merged_stcp_file])
                mergecap(merged_stcp_file,data[0],dir=True)
                streams = debug_get_streams(merged_stcp_file, \
                          'ssl.record.content_type==23 and tcp.port=='+\
                        str(data[1]),options=options)
                for stream in streams:
                    comparison[data[0]][stream] = get_frames_hashes( \
                    merged_stcp_file,port=data[1],stream=stream,options=options)
                    shared.debug(3,["Here is comparison[",data[0],"]:",\
                                    stream,":",comparison[data[0]][stream] ])
            else:
                print "Error! stcppipe is always port type now.\n"
                exit(1)
                '''for file in os.listdir(data[0]):
                    #note here that files map one to one with streams
                    #counter-intuitively we need to call get_all_ssl... WITHOUT
                    #the stcp flag, because we need separate hash lists per stream
                    #so we pass the exact stream files one by one 
                    #(i.e. we're not aggregating here)
                    stream = get_stream_from_stcp_filename(file)
                    shared.debug(1,["From stcppipe filename",file, \
                                    "got stream number:",stream])
                    comparison[data[0]][stream]= \
                    get_all_ssl_hashes_from_capfile(capfile= \
                    os.path.join(data[0],file),port=data[1],in_options=options)'''
        else: #means tshark was used but we still want per stream stuff
            streams = debug_get_streams(data[0], \
                      'ssl.record.content_type==23 and tcp.port=='+str(data[1])\
                      ,options=options)
            for stream in streams:
                comparison[data[0]][stream] = get_frames_hashes(data[0],\
                                              port=data[1],stream=stream,\
                                                options=options)
                shared.debug(3,["Here is comparison[",data[0],"]:",\
                                    stream,":",comparison[data[0]][stream] ])

    #first find hashes which are different for a high level view
    hashes1 = set()
    hashes2 = set()
    for val in comparison[data1[0]].values():
            for val2 in val.values():
                hashes1.update(set(val2))
    for val in comparison[data2[0]].values():
            for val2 in val.values():
                hashes2.update(set(val2))

    #just a comparison of flat (unique) lists
    shared.debug(1,["Length of list of hashes for file",capfile1," is: ", len(hashes1)])
    shared.debug(1,["Length of list of hashes for file",capfile2," is: ", len(hashes2)])
    shared.debug(2,["All hashes for file",capfile1,": ",hashes1])
    shared.debug(2,["All hashes for file",capfile2,": ",hashes2])
     
    #mismatches are (union-intersection) of two sets:   
    diff_hashes = hashes1.symmetric_difference(hashes2)
    
    
    
    #the next step is a large cartesian product mapping every match/mismatch
    #THIS TAKES TIME - so don't do this if you don't want to wait!
    ok_frames_streams1 = {}
    ok_frames_streams2 = {}
    ok_frames_1 = []
    ok_frames_2 = []
    for stream1,val1 in comparison[data1[0]].iteritems():
        for stream2,val2 in comparison[data2[0]].iteritems():
            for frame1, hash1 in val1.iteritems():
                for frame2, hash2 in val2.iteritems():
                    shared.debug(4,["frame1, frames 2 are now: " , frame1, " ", frame2])
                    for hasha in hash1:
                        for hashb in hash2:
                            shared.debug(4,["Trying hashes1,2: ",hasha," ",hashb])
                            if hasha == hashb:
                                shared.debug(3,\
                                ["Found a match between frame1 and frame2: ", \
                                 frame1,hasha, " ",frame2,hashb, "in stream1:"\
                                ,stream1,",stream2:",stream2])
                                ok_frames_1.append(frame1)
                                ok_frames_2.append(frame2)
                
    shared.debug(2,["OKFrames1: ",list(set(ok_frames_1))])
    shared.debug(2,["OKFrames2: ",list(set(ok_frames_2))])
    shared.debug(1,["Number of frames OK in first file: ", \
                    len(set(ok_frames_1))])
    shared.debug(1,["Number of frames OK in second file: ", \
                    len(set(ok_frames_2))])
    print "\n\n\n"
    print "============================================"
    print "Here is the entire comparison datastructure"
    print "============================================"
    print comparison
    print "\n\n\n"
    for val in comparison[data1[0]].values():
        for frame in [val2 for val2 in val.iterkeys() if val2 not in ok_frames_1]:
            print "Hash of segment in frame " + str(frame) + " in " + capfile1 \
                + " was not found in any frame in " + capfile2 
    for val in comparison[data2[0]].values():
        for frame in [val2 for val2 in val.iterkeys() if val2 not in ok_frames_2]:
            print "Hash of segment in frame " + str(frame) + " in " + capfile2 \
                + " was not found in any frame in " + capfile1
    shared.debug(1,["All hashes which didn't match: ",diff_hashes])



#designed to return a dict of all hashes per frame, optionally
#filtered by stream
def get_frames_hashes(capfile,port,stream='',options=[]):    
    frames_hashes = {}
    #Run tshark once to get a list of frames with ssl app data in them
    filterstr = 'ssl.record.content_type==23 and tcp.port=='+str(port)
    if (stream):
        filterstr += (' and tcp.stream==' + stream)
    try:
        frames_str = tshark(capfile,field='frame.number', \
                            filter= filterstr,options=options)
    except:
        print 'Exception in tshark'
        return -1
    
    ssl_frames = shared.pisp(frames_str)
    shared.debug(1,['need to process this many frames:', len(ssl_frames)])
    for frame in ssl_frames:
        frames_hashes[frame]= [] #array will contain all hashes for that frame
    
    ssl_app_data = tshark(capfile,field='ssl.app_data',frames=ssl_frames, \
                          options=options)
    #ssl.app_data will return all encrypted segments separated by commas
    #WITHIN each frame, and each frame consecutively is separated by a newline
    #so first we split ONLY on the (platform dependent) newline to get
    #a chunk of ssl app data for EACH FRAME
    app_data_output = shared.pisp(ssl_app_data)
    shared.debug(4,app_data_output)
    #now app_data_output is a list, each element of which is the complete
    #output of ssl.app_data for each frame consecutively
    x=0
    for frame in ssl_frames:
        #now we are looking at the ssl app data for a single frame -
        #need to split it into segments
        segments = app_data_output[x].split(',')
         # make sure that segments is empty if there's no data!
        segments = filter(None,segments)
        frames_hashes[frame].extend(get_ssl_hashes_from_ssl_app_data_list(segments))
        shared.debug(3,["Frame: ", frame, frames_hashes[frame]])
        x += 1
    
    return frames_hashes


def debug_get_streams(capfile,filterstr='',options=[]):
    streams_output = tshark(capfile,field='tcp.stream',filter=filterstr,\
                    options=options)
    streams = list(set(shared.pisp(streams_output)))
    shared.debug(2,["This is the list of tcp streams: ", streams])
    return streams

mfile = ''
#Look up libpcap file format for more detail
def write_pkt(data, dest):
    global mfile
    pkt_len = 54+len(data)
    import struct
    hex_len = struct.pack("!I", pkt_len)
    pkt_hdr = bytearray("\x00\x00\x00\x00") + "\x00\x00\x00\x00" + hex_len + hex_len

    eth_hdr = bytearray("\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x08\x00")

    ip_hdr = bytearray("\x45")      #4 bits IPv4 + 4 bits header length
    ip_hdr += "\x00"     #Diff.Ser
    ip_hdr += struct.pack('!H', (pkt_len-len(eth_hdr))) #total packet length, min 20
    ip_hdr += "\x00\x00"     #id
    ip_hdr += "\x00\x00" #3 bits flags  + 13 bits offset
    ip_hdr += "\x10"     #TTL
    ip_hdr += "\x06"     #Protocol :TCP
    ip_hdr += "\xac\xc8" #header checksum
    ip_hdr += "\x7f\x00\x00\x01"  #source: 127.0.0.1
    ip_hdr += "\x7f\x00\x00\x01"  #dest: 127.0.0.1
    
    tcp_hdr = bytearray()
    if dest==1:
        tcp_hdr += "\x1f\x90" #source port: 8080
        tcp_hdr += "\xe0\x2c" #dest port: 57388
    else:
        tcp_hdr += "\xe0\x2c" #dest port: 57388
        tcp_hdr += "\x1f\x90" #source port: 8080
    tcp_hdr += "\x00\x00\x00\x00" #seq number
    tcp_hdr += "\x00\x00\x00\x00" #ack number
    tcp_hdr += "\x50"     # 4 bits TCP header size (in 32-bit units)+ 3 bit reserved + 1 bit flags
    tcp_hdr += "\x18"     #flags
    tcp_hdr += "\x01\x00" #window size
    tcp_hdr += "\x00\x00" #checksum
    tcp_hdr += "\x00\x00" #urgent pointer
    
    mfile.write(pkt_hdr + eth_hdr + ip_hdr + tcp_hdr +data)
    mfile.flush()
    
def build_filterstr(stream='',port=-1):
    filterstr = 'ssl.record.content_type==23'
    if (port > 0):
        filterstr = filterstr + ' and tcp.port=='+str(port)
    if (stream):
        filterstr = filterstr + ' and tcp.stream=='+str(stream)
    return filterstr

def build_option_list(in_options=[], base='http'):
    if not in_options:
        return [[]]
        
    option_boolean_lists=[]
    #build a list of possible options flags to try
    if (in_options):
        for option in in_options:
            if 'port' in option: #very ugly hack just to try
                option_boolean_lists.append([option,''])
            else:
                option_boolean_lists.append([option+':True',option+':False'])
        option_all_lists = list(itertools.product(*option_boolean_lists))
        shared.debug(3,option_all_lists)
    else:
       option_all_lists=[]
       
    options_permutations_list = []
    
    for option_list in option_all_lists:
        option_list_tmp = filter(None,list(option_list))
        options_permutations_list.append(option_list_tmp)
    
    return options_permutations_list