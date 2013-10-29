var reqPageMarked;
var reqCheckEscrowtrace;
var isPageMarkedResponded = false;
var isCheckEscrowtraceResponded = false;
var is_accno_entered = false;
var is_sum_entered = false;
var pressed_blue_once = false;
var was_clearcache_called = false;
var consoleService;
var prefs;
var port;
var first_window;


consoleService = Components.classes["@mozilla.org/consoleservice;1"].getService(Components.interfaces.nsIConsoleService);
prefs = Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService);
port = Components.classes["@mozilla.org/process/environment;1"].getService(Components.interfaces.nsIEnvironment).get("FF_to_backend_port");
Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService).getBranch("extensions.lspnr.").setBoolPref("start_new_session", false);
first_window = Components.classes["@mozilla.org/process/environment;1"].getService(Components.interfaces.nsIEnvironment).get("FF_first_window");
//let all subsequent windows know that they are not the first window, so they could skip some initialization
Components.classes["@mozilla.org/process/environment;1"].getService(Components.interfaces.nsIEnvironment).set("FF_first_window", "false");
//setting homepage should be done from here rather than defaults.js in order to have the desired effect. FF's quirk.
Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService).getBranch("browser.startup.").setCharPref("homepage", "chrome://lspnr/content/home.html");


if (first_window === "true" ) {
	//Let the backend know that it can remove the splashscreen
	var reqStarted = new XMLHttpRequest();
	reqStarted.open("HEAD", "http://127.0.0.1:"+port+"/started", true);
	reqStarted.send();    

	setProxyPrefs();
}


//Simply send a HEAD request to the python backend to 127.0.0.1:2222/blabla. Backend treats "/blabla" not as a path but as an API call
//Backend responds with HTTP headers "response":"blabla" and "value":<value from backend>
function pageMarked(){
	var button_blue = document.getElementById("button_blue");
	var button_grey1 = document.getElementById("button_grey1");
	var textbox_sum = document.getElementById("textbox_sum");
	var textbox_accno = document.getElementById("textbox_accno");
	var label_accno = document.getElementById("label_accno");
	var label_accno_white = document.getElementById("label_accno_white");
	var label_sum = document.getElementById("label_sum");
	var label_sum_white = document.getElementById("label_sum_white");
	
	button_blue.hidden = true;
	button_grey1.hidden = false;

	if (!pressed_blue_once) {
		label_accno.hidden = true;
		label_accno_white.hidden = false;
		label_sum.hidden = true;
		label_sum_white.hidden = false;
		textbox_sum.disabled = true;
		textbox_accno.disabled = true;
		pressed_blue_once=true;
	}
	var accno_str = textbox_accno.value;
	var sum_str = textbox_sum.value;
	var request_str = "http://127.0.0.1:"+port+"/page_marked";
	//Check if we are testing. In production mode, accno and sum are known in advance of opening FF
	if (accno_str){
		request_str += "?accno=";
		request_str += accno_str;
		request_str += "&sum=";
		request_str += sum_str;
	}
	if (was_clearcache_called){
		request_str += "&was_clearcache_called=yes";
	}
	else{
		request_str += "&was_clearcache_called=no";
	}
	
	reqPageMarked = new XMLHttpRequest();
	reqPageMarked.onload = responsePageMarked;
	reqPageMarked.open("HEAD", request_str, true);
	reqPageMarked.send();

	log("Finding HTML in our data");
	log_toolbar("Finding HTML in our data");
	isPageMarkedResponded = false;
	setTimeout(responsePageMarked, 1000, 0);
}

//backend responds to page_marked with either "success" ot "clear_ssl_cache"
function responsePageMarked (iteration) {
    if (typeof iteration == "number"){
        if (iteration > 20){
            log("Oracle is taking more than 20 seconds to respond. Please check your internet connection and try again");
            return;
        }
        if (!isPageMarkedResponded) setTimeout(responsePageMarked, 1000, ++iteration);
        return;
    }
    //else: not a timeout but a response from the server
    isPageMarkedResponded = true;
	var query = reqPageMarked.getResponseHeader("response");
	var value = reqPageMarked.getResponseHeader("value");
	if (query != "page_marked") {
		log("Internal error. Wrong response header: "+ query);
		log_toolbar("Internal error. Wrong response header: "+ query);
	}
	if (value == "success") {
		log("SUCCESS finding HTML in our data");
		log_toolbar("SUCCESS finding HTML in our data");
		setTimeout(checkEscrowtrace, 1000);
	}
	else if (value == "clear_ssl_cache") {
		//var yellow_button = document.getElementById("button_yellow");
		//yellow_button.hidden = false
		clearSSLCache();
		log("Please refresh this page and press the blue button again");
		log_toolbar("Please refresh this page and press the blue button again");
	}
	else if (value == "failure") {
		log("FAILURE finding HTML. Please let the developers know");
		log_toolbar("FAILURE finding HTML. Please let the developers know");
		terminate();
	}
	else {
 		log("Internal Error. Unexpected value: "+value+". Please let the developers knows");
 		log_toolbar("Internal Error. Unexpected value: "+value+". Please let the developers knows");
 		terminate();
	}
}

function checkEscrowtrace(){
	log("Finding HTML in escrow data");
	log_toolbar("Finding HTML in escrow data");

	reqCheckEscrowtrace = new XMLHttpRequest();
	reqCheckEscrowtrace.onload = responseCheckEscrowtrace;
	reqCheckEscrowtrace.open("HEAD", "http://127.0.0.1:"+port+"/check_escrowtrace", true);
	reqCheckEscrowtrace.send();

	setTimeout(responseCheckEscrowtrace, 1000, 0);
}


function responseCheckEscrowtrace (iteration) {
    if (typeof iteration == "number"){
        if (iteration > 40){
            log("Oracle is taking more than 40 seconds to respond. Please check your internet connection and try again");
            return;
        }
        if (!isCheckEscrowtraceResponded) setTimeout(responseCheckEscrowtrace, 1000, ++iteration);
        	return;
    }
    //else: not a timeout but a response from the server
    isCheckEscrowtraceResponded = true;
	var query = reqCheckEscrowtrace.getResponseHeader("response");
	var value = reqCheckEscrowtrace.getResponseHeader("value");
	if (query != "check_escrowtrace") {
		log("Internal error. Wrong response header: "+ query);
		log_toolbar("Internal error. Wrong response header: "+ query);
		terminate();
	}
	if (value == "success") {
		log("SUCCESS finding HTML in escrow's data");
		log_toolbar("SUCCESS finding HTML in escrow's data");
		alert("Congratulations! Paysty can be used with your bank's website. You can either start the fun again on Paysty's tab or close Firefox");
		terminate();
	}
	else if (value == "failure") {
		log("FAILURE finding HTML in escrow's data. Please let the developers know");
		log_toolbar("FAILURE finding HTML in escrow's data. Please let the developers know");
		terminate();
	}
	else {
 		log("Internal Error. Unexpected value: "+value+". Please let the developers knows");
 		log_toolbar("Internal Error. Unexpected value: "+value+". Please let the developers knows");
 		terminate();
	}
}

function setProxyPrefs(){
	var port = Components.classes["@mozilla.org/process/environment;1"].getService(Components.interfaces.nsIEnvironment).get("FF_proxy_port");
	var port_int = parseInt(port);
	proxy_prefs = prefs.getBranch("network.proxy.");
	proxy_prefs.setIntPref("type", 1);
	proxy_prefs.setCharPref("http","127.0.0.1");
	proxy_prefs.setIntPref("http_port", port_int);
	proxy_prefs.setCharPref("ssl","127.0.0.1");
	proxy_prefs.setIntPref("ssl_port", port_int);
}

function accno_input() {
	if (is_accno_entered){
		return;
	}
	is_accno_entered = true;	
	if (is_sum_entered){
		 var button_blue = document.getElementById("button_blue");
		 var button_grey1 = document.getElementById("button_grey1");
		 button_grey1.hidden = true;
		 button_blue.hidden = false;
	}
}

function sum_input() {
	if (is_sum_entered){
		return;
	}
	is_sum_entered = true;
	if (is_accno_entered){
		 var button_blue = document.getElementById("button_blue");
		 var button_grey1 = document.getElementById("button_grey1");
		 button_grey1.hidden = true;
		 button_blue.hidden = false;
	}
}

function clearSSLCache() {
 //    var button_yellow = document.getElementById("button_yellow");
 //    var button_grey2 = document.getElementById("button_grey2");
	// button_yellow.hidden = true
	// button_grey2.hidden = false
	Components.classes["@mozilla.org/security/sdr;1"].getService(Components.interfaces.nsISecretDecoderRing).logoutAndTeardown();
	was_clearcache_called = true;
	var button_blue = document.getElementById("button_blue");
	var button_grey1 = document.getElementById("button_grey1");
	button_grey1.hidden = true;
	button_blue.hidden = false;
}


//Check if user wants to start a new banking session
checkNewSession()
function checkNewSession() {
    var branch = Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService).getBranch("extensions.lspnr.");
    var value = branch.getBoolPref("start_new_session");
    if (value !== true){
        setTimeout(checkNewSession, 1000);
        return;
    }
   	var button_blue = document.getElementById("button_blue");
	var button_grey1 = document.getElementById("button_grey1");
	var textbox_sum = document.getElementById("textbox_sum");
	var textbox_accno = document.getElementById("textbox_accno");
	var label_accno = document.getElementById("label_accno");
	var label_accno_white = document.getElementById("label_accno_white");
	var label_sum = document.getElementById("label_sum");
	var label_sum_white = document.getElementById("label_sum_white");
	
	button_blue.hidden = true;
	button_grey1.hidden = false;

	label_accno.hidden = false;
	label_accno_white.hidden = true;
	label_sum.hidden = false;
	label_sum_white.hidden = true;
	textbox_sum.disabled = false;
	textbox_sum.value = "";
	textbox_accno.disabled = false;
	textbox_accno.value = "";
	pressed_blue_once=false;

	is_accno_entered = false;
	is_sum_entered = false;

    branch.setBoolPref("start_new_session", false);
    setTimeout(checkNewSession, 3000);
}

function terminate(){
    reqTerminate = new XMLHttpRequest();
    reqTerminate.open("HEAD", "http://127.0.0.1:"+port+"/terminate", true);
    reqTerminate.send();    
}

function log_toolbar(string){
    var branch = Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService).getBranch("extensions.lspnr.");
    branch.setCharPref("msg_toolbar", string);
}

function log(string){
	var branch = Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService).getBranch("extensions.lspnr.");
	branch.setCharPref("msg_ipc", string);
}

//don't allow any new tabs for the space of 5 secs
//This is to prevent FF from opening a new home tab on launch 
function closeTabs(){
	for (var j = 0; j < 50; j++){
		setTimeout(function(){
			try{
				var tabs = gBrowser.tabs;
		    	for (var i=0; i < tabs.length; i++) {
		    		if (tabs[i].pinned === false) {
		    			tabs[i].collapsed = true;
		    		}
		    	}
		    }
			catch(err){
				return;
			}
		},j*100);
	}
}

var lspnr_prefs = Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService).getBranch("extensions.lspnr.");
if (lspnr_prefs.getBoolPref("first_run") === false){
	closeTabs()
}
else {
	//pin the addon tab on first run. It should remain pinned on subsequent runs
	setTimeout(function(){
	    lspnr_prefs.setBoolPref("first_run", false);
	    //load new tab in foreground
		var tab = gBrowser.loadOneTab("chrome://lspnr/content/home.html", null, null, null, false);
		gBrowser.pinTab(tab);
		closeTabs()
	}, 1000);
}	



setTimeout(getToolbarMsg, 3000);
function getToolbarMsg() {
    var branch = Components.classes["@mozilla.org/preferences-service;1"].getService(Components.interfaces.nsIPrefService).getBranch("extensions.lspnr.");
    var msg = branch.getCharPref("msg_toolbar");
    var info = document.getElementById("label_info");
    var cur_msg = info.value;
    if (msg == cur_msg){
        setTimeout(getToolbarMsg, 10);
        return;
    }
    info.value = msg;
    setTimeout(getToolbarMsg, 10);
}