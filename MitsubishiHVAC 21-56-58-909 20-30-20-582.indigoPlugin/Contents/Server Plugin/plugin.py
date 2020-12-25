#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2016, Perceptive Automation, LLC. All rights reserved.
# http://www.indigodomo.com

import indigo
import json
import os
import sys
import random
import httplib
import urllib
import base64
import hashlib
import datetime



# Note the "indigo" module is automatically imported and made available inside
# our global name space by the host process.

################################################################################
kHvacModeEnumToStrMap = {
	indigo.kHvacMode.Cool				: u"cool",
	indigo.kHvacMode.Heat				: u"heat",
	indigo.kHvacMode.HeatCool			: u"auto",
	indigo.kHvacMode.Off				: u"off",
	indigo.kHvacMode.ProgramHeat		: u"program heat",
	indigo.kHvacMode.ProgramCool		: u"program cool",
	indigo.kHvacMode.ProgramHeatCool	: u"program auto"
}

kFanModeEnumToStrMap = {
	indigo.kFanMode.AlwaysOn			: u"always on",
	indigo.kFanMode.Auto				: u"auto"
}



def _lookupActionStrFromHvacMode(hvacMode):
	return kHvacModeEnumToStrMap.get(hvacMode, u"unknown")

	
def _lookupActionStrFromFanMode(fanMode):
	return kFanModeEnumToStrMap.get(fanMode, u"unknown")

class kumoConfig:
		def __init__ (self,kcDict):
			self.address = kcDict["address"]
			self.label = kcDict["label"];
			self.password = kcDict['password']
			self.S = 0
			self.cryptoSerial = kcDict['cryptoSerial']
			self.unitType = kcDict['unitType']
			self.W = '44c73283b498d432ff25f5c8e06a016aef931e68f0a00ea710e36e6338fb22db'
			self.connectionStatus = 10
			
class unitGroup:
	def __init__ (self,unitList):
		devIdList =[]
		for unit in unitList:
			devIdList.append(unit)	



################################################################################
class Plugin(indigo.PluginBase):
	########################################
	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
		super(Plugin, self).__init__(pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
		self.debug = False
		self.simulateTempChanges = True		# Every few seconds update to random temperature values
		self.simulateHumidityChanges = True	# Every few seconds update to random humidity values
		self.refreshDelay = 1				# Simulate new temperature values every 1 seconds
	class kumo:
		def __init__ (self, configuration):
			#configlist - The entire configuration - delivered as a list.  4 items: The first 3 items are Dict.
			# [0] - username, device, token
			# [1] - 'installer_number', u'lastUpdate', u'installer_name', u'sendAnalytics'
			# [2] (systemDict) - u'lastUpdate', u'level', u'zoneTable', u'children', u'version', u'lastScheduleChange', u'label', u'id'
			# [3] - Unicode type, not sure the value (not a dictionary)
			self.configList = json.loads(configuration)  
			
			self.systemDict = self.configList[2]  
			
			#children - The first level of the unit heirarchy.  List of subsystems.  Only one item in the list
			# [0] - [u'lastUpdate', u'$$hashKey', u'network', u'level', u'zoneTable', u'children', u'label', u'lastScheduleChange', u'id']
			#self.children = self.systemDict['children']
			#self.childrenDict = self.children[0]
			
			#grandchildren - The second level of hte unit Heirarchy.  List of subsystems.  3 items in this list
			#[0][u'lastUpdate', u'$$hashKey', u'reportedCondition', u'level', u'zoneTable', u'children', u'label', u'lastScheduleChange', u'id']
			#[1][u'lastUpdate', u'$$hashKey', u'reportedCondition', u'level', u'zoneTable', u'children', u'label', u'lastScheduleChange', u'id']
			#[2][u'lastUpdate', u'$$hashKey', u'reportedCondition', u'level', u'zoneTable', u'children', u'label', u'lastScheduleChange', u'id']
			#self.grandChildren = self.childrenDict['children'];
			#self.grandChildrenDict0 = self.grandChildren[0]
			#self.grandChildrenDict1 = self.grandChildren[1]
			#self.grandChildrenDict2 = self.grandChildren[2]
		
		
		########################################
		# parseZones takes a config database that was downloaded from KumoCloud
		# and parses it into a dictionary of keys
		# each entry in the dictionary is a kumoConfig element
		# The dictionary is indexed by the labels of the units
		###########################################	
		def parseZones(self, pDictionary, keys):
			# Parse the children from each zone
			zones = pDictionary['zoneTable']
			for i in range(0,len(zones)):
				currentKey = zones.keys()[i]
				kcConfig = kumoConfig(zones[currentKey])
				keys[kcConfig.label] = kcConfig

			# recurse through the children to find more zones
			for j in range(0,len(pDictionary['children'])):
				listOfDictionaries = pDictionary['children']
				self.parseZones(listOfDictionaries[j], keys)
	


#############################################################
# Some utility functions for manipulating number formats
# useful in calculating hash and formatting messages for sending over http
###########
	# convert a string representation of a long hex nubmer to an array of 2-byte values
	def hexString2List(self, strng):
		outputArray = []
		for i in range(0,len(strng),2):
			outputArray.append(int(strng[i:i+2],16))	
		return(outputArray)
	
	# convert an array of 2-byte values to a string with a series  2-character representations of the Hex values
	def list2HexString2(self, lst):
		outputStrng =""
		for i in range(0, len(lst),1):
			outputStrng = outputStrng + chr(lst[i])
		return(outputStrng)

	#Takes a string and calculates a sha256 hash of the string, returning a string representation of that hash 	
	def hash256(self, lst):
		m = hashlib.sha256()
		m.update(lst)
		outputHash = m.hexdigest()
		return(outputHash)
	

	def generateHash(self,cserial,password, body):
			#{"c":{"indoorUnit":{"status":{}}}});
		#dt = dt.replace(": ", ":")
		w = "44c73283b498d432ff25f5c8e06a016aef931e68f0a00ea710e36e6338fb22db"
		W = self.hexString2List(w)
		S = 0
		p = base64.b64decode(password)

		#address = "192.168.1.21"
		#cserial = "0123b1b5d27a84c8ee"

		pdt = p+body
		dt1 = self.hash256(pdt)
		dt1_l = self.hexString2List(dt1)

		dt2 = ''
		for i in range (0,88):
			dt2 += '00'

		dt3 = self.hexString2List(dt2)
		dt3[64] = 8
		dt3[65] = 64
		dt3 = dt3[:32] + dt1_l + dt3[32+len(dt1_l):]
		dt3[66] =  S

		cryptoserial = self.hexString2List(cserial)


		dt3[79] = cryptoserial[8]
		dt3[80] = cryptoserial[4]
		dt3[81] = cryptoserial[5]
		dt3[82] = cryptoserial[6]
		dt3[83] = cryptoserial[7]
		dt3[84] = cryptoserial[0]
		dt3[85] = cryptoserial[1]
		dt3[86] = cryptoserial[2]
		dt3[87] = cryptoserial[3]
		print(dt3)
		dt3 = W + dt3[32:]
		print(dt3)


		dt4 = self.list2HexString2(dt3)
		return(self.hash256(dt4))


	def convertC2F(self, cTemp):
		returnValue =  cTemp
		try:
			tmp = float(cTemp)
		except:
			self.logger.info("convertC2F  Error:  cTemp  is not a string or Float: !" + str(cTemp) + "|!")	
		else:
			returnValue = (32+int(float(cTemp)*1.8))
		return returnValue
		
	def convertC2Fish(self, cTemp):
			#Mitsubishi seems to use some weird rounding and if you don't send the expected
			#number, it doesn't set the temp correctly. It is Celcius'ish
			# This properly converts those numbers back to Farenheit
			# Haven't yet used this routing but wrote it so I don't loose the information
			fTemp1 = cTemp*2 +30
			tmp = 0
			tmp = 1 if cTemp > 11 else tmp;
			tmp = 2 if cTemp > 18.5 else tmp;
			tmp = 3 if cTemp > 20 else tmp;
			tmp = 4 if cTemp > 30 else tmp;
			return(fTemp1-tmp);


		
	def convertF2Cish(self, fTemp):
		#Mitsubishi seems to use some weird rounding and if you don't send the expected
		#number, it doesn't set the temp correctly. It is Celcius'ish
		cTemp1 = (fTemp - 50)*.5 +10
		tmp = 0
		tmp = .5 if fTemp > 52 else tmp;
		tmp = 1.0 if fTemp > 64 else tmp;
		tmp = 1.5 if fTemp > 68 else tmp;
		tmp = 2.0 if fTemp > 87 else tmp;
		return (cTemp1+tmp);

	###############
	# generageDeviceList is called when the device config menu is opened
	# Device List is a dynamic list that allows the user to pick from
	# the actual HVAC devices that have been detected on the network when creating a new indigo device
	##	
	def generateDeviceList(self, filter="", valuesDict=None, typeId="", targetId=0):		
		pluginConfigFolder = indigo.server.getInstallFolderPath() + "/Preferences/Plugins/" 
		#self.logger.info(pluginConfigFolder)

		if os.path.isdir(pluginConfigFolder):
			configDir = pluginConfigFolder + self.pluginId
			f = open(configDir+"/kumoConfig.txt", "r")
			config = f.read()
			f.close()
					
			test = self.kumo(config)
			configArray = {}
			myArray = []
			test.parseZones(test.systemDict, configArray)
			for i in range(0,len(configArray)):
				myArray.append((configArray.keys()[i], configArray.keys()[i]))
		else:
			self.logger.info("Mitsubishi HVAC - Can't find configuration file")
			myArray[0] = (u"no devices found", u"no devices found")
		
		return myArray


	###############
	#validateDeviceConfigUi - called when a device configuration is saved
	# can be used to inspect and/or change the values in the vlauseDict
	##############
	def validateDeviceConfigUi(self, valuesDict=None, typeId="", devId=0):
		# Fetch all the other parameters for the unit that has been selected
		pluginConfigFolder = indigo.server.getInstallFolderPath() + "/Preferences/Plugins/" 
		indigo.server.log("typeId= ")
		indigo.server.log(typeId)

		
		if os.path.isdir(pluginConfigFolder):
			configDir = pluginConfigFolder + self.pluginId
			f = open(configDir+"/kumoConfig.txt", "r")
			config = f.read()
			f.close()
					
			test = self.kumo(config)
			configArray = {}
			myArray = []
			test.parseZones(test.systemDict, configArray)
			
		if typeId== "mitsubishiHVACDuctless":	
			
			unitConfig = configArray[valuesDict['label']]
			valuesDict['address']=unitConfig.address
			valuesDict['password']=unitConfig.password
			valuesDict['W']=unitConfig.W
			valuesDict['cryptoSerial']=unitConfig.cryptoSerial
			valuesDict['unitType']=unitConfig.unitType
			valuesDict['S']=unitConfig.S
		elif typeId== "mitsubishiHVACGroup":
			self.logger.info(valuesDict["groupMembers"])
			indigo.server.log("Group Init")
			tmp = unitGroup(valuesDict["groupMembers"])
			
				
			#unitConfig = configArray[valuesDict['label']]
		else:
			self.logger.info("Mitsubishi HVAC - Can't find configuration file")
		return (True, valuesDict)



	def DownloadButtonPressed(self, valuesDict): #, typeId, devId):
		# do whatever you need to here
		#   typeId is the device type specified in the Devices.xml
		#   devId is the device ID - 0 if it's a new device
		
		pluginConfigFolder = indigo.server.getInstallFolderPath() + "/Preferences/Plugins/" 
		if os.path.isdir(pluginConfigFolder):
			configDir = pluginConfigFolder + self.pluginId
			
			if not os.path.isdir(configDir):
				os.mkdir(configDir)
				self.logger.info("created Directory: "+configDir)
		
		#########################################################
		#Use the user name and password to reach out to the KumoCloud
		#server and download the account configuration database
		#########################################################
		msg = {
			"username": valuesDict["userNameText"],
			"password": valuesDict["acctPasswordText"],
			"appVersion": "2.2.0"
		}
		post_data = json.dumps(msg);

		headers =  {
					'Accept': 'application/json, text/plain, */*',
					'Accept-Encoding': 'gzip, deflate, br',
					'accept-Language': 'en-US,en',
					'Content-Length': len(post_data),
					'Content-Type': 'application/json'
				}
		body = post_data
		self.logger.info(body, headers)
		conn = httplib.HTTPSConnection('geo-c.kumocloud.com')

		conn.request("POST","/login" , body, headers)
		response = conn.getresponse()
		downloadedConfig = response.read()
		f = open(configDir+"/kumoConfig.txt", "w+")
		f.write(downloadedConfig)
		f.close

		return valuesDict
	






##########################################################################
#Section:
#  Messaging to the HVAC Units
##########################################################################

	######################
	# All of the routines call this utility to manage sending messages to the unit
	# The message content has already been formatted
	# this routine manages retries if a proper response isn't received
	def sendMessageToHVAC(self, dev, body):
		address = dev.pluginProps['address']
		cserial = dev.pluginProps['cryptoSerial']
		password = dev.pluginProps['password']
		name = dev.name
		#self.logger.info(body)
		success = False
		responseDirectory = {}
		#self.logger.info("Sending message to address: "+ address)
		headers =  {
					'Accept': 'application/json, text/plain, */*',
					'Content-Type': 'application/json'
				}
			
		maxRetryTimes = 5
		for retryTimes in range(maxRetryTimes):
			try:
				conn = httplib.HTTPConnection(address, timeout=.2  )
			except Exception as exceptInstance:		
				self.logger.debug( "HTTP Error: Connection failed "+ address + " had exception: " + str(type(exceptInstance)))
			else:
				try: 					
					conn.request("PUT",'/api?m=' + self.generateHash(cserial, password, body) , body, headers)
					response = conn.getresponse()		
					theResponse = response.read()
				except Exception as exceptInstance:
					self.logger.debug( "HTTP Error: PUT failed "+ address + " had exception: " + str(type(exceptInstance)))
					
				else:
					responseDirectory = json.loads(theResponse)
					if	"r" in responseDirectory.keys():
						success = True	
						#self.logger.info(responseDirectory)
					else:
						self.logger.debug("Bad response from unit " + address + "  Response received: "+str(theResponse))
					self.restoreConnectionStatus(dev)	
					break
				
			self.logger.debug("Retrying message to address: "+ address + " times= " + str(retryTimes) )
		
		if success == False:
			self.reduceConnectionStatus(dev)
			
		return(success, responseDirectory)



	######################
	# Method to send messages to HVAC units and collect status from the HVAC units
	# Calls sendMessageToHVAC to actually communicate with the units
	# then populates Indigo with the results as appropriate
	def unitCommunication(self, dev, action, actionValue):
		
		if not dev.deviceTypeId == "mitsubishiHVACGroup":
			commandEntry ={}
			if action != "status":
				commandEntry = {action:actionValue}
				self.logger.info(u"Sending %s command to %s with setting \"%s\" " % (action, dev.name, actionValue))
			jBody = json.dumps({"c":{"indoorUnit":{"status":commandEntry}}})
			stateOfUnit = self.sendMessageToHVAC(dev,jBody)
			if stateOfUnit[0] == True :	
				if action != "status":
					self.logger.info(u"Command %s \"%s\" successfully sent to %s " % (action, actionValue, dev.name))							
				statusDict = stateOfUnit[1]["r"]["indoorUnit"]["status"]
				if "roomTemp" in statusDict:
					if statusDict['roomTemp'] != None:
						dev.updateStateOnServer('displayUnitTemp',value=self.convertC2F(statusDict['roomTemp']))
						
				if "fanSpeed" in statusDict:
					dev.updateStateOnServer('displayFanSpeed',value=statusDict['fanSpeed'])
					
				if "vaneDir" in statusDict:
					dev.updateStateOnServer('displayVaneDirection',value=statusDict['vaneDir'])
					
				if "spCool" in statusDict:
					if statusDict['spCool'] != None:
						dev.updateStateOnServer('displaySetpointCool',self.convertC2F(statusDict['spCool']))
						dev.updateStateOnServer('setpointCool', self.convertC2F(statusDict['spCool']))
						#dev.updateStateOnServer('displaySetpointTemp',self.convertC2F(statusDict["spCool"]))					
					
				if "spHeat" in statusDict:
					if statusDict['spHeat'] != None:
						dev.updateStateOnServer('displaySetpointHeat',self.convertC2F(statusDict['spHeat']))
						dev.updateStateOnServer('setpointHeat', self.convertC2F(statusDict['spHeat']))
						#dev.updateStateOnServer('displaySetpointTemp',self.convertC2F(statusDict["spHeat"]))
					
				if "mode" in statusDict:
					dev.updateStateOnServer('displayHVACMode',statusDict['mode'])
					if statusDict['mode']=="heat": 
						dev.updateStateOnServer('hvacOperationMode', indigo.kHvacMode.Heat)
						if "spHeat" in statusDict:
							if statusDict['spHeat'] != None:
								dev.updateStateOnServer('displaySetpointTemp',self.convertC2F(statusDict["spHeat"]))
					elif statusDict['mode']=="cool": 							
						dev.updateStateOnServer('hvacOperationMode', indigo.kHvacMode.Cool)
						if "spCool" in statusDict:
							if statusDict['spCool'] != None:
								dev.updateStateOnServer('displaySetpointTemp',self.convertC2F(statusDict["spCool"]))
			else:
				if action != "status":
					self.logger.info(u"Command %s \"%s\" failed to send to %s " % (action, actionValue, dev.name))
				
			if action == "status":
				# Next Get the Temp Sensor States States			
				jBody = json.dumps({"c":{"sensors":{}}})
				stateOfUnit = self.sendMessageToHVAC(dev,jBody)
				if stateOfUnit[0] == True:
					
					statusDict = stateOfUnit[1]["r"]["sensors"]["0"]
					dev.updateStateOnServer('sensorHumidity',statusDict['humidity'])
					dev.updateStateOnServer('sensorRSSI',statusDict['rssi'])
					dev.updateStateOnServer('sensorBatteryLevel',statusDict['battery'])
				
				# Next Get the WIFI Adaptor States States			
				jBody = json.dumps({"c":{"adapter":{"status":{},"info":{}}}})
				stateOfUnit = self.sendMessageToHVAC(dev,jBody)
				if stateOfUnit[0] == True:
					statusDict = stateOfUnit[1]["r"]["adapter"]["status"]
					dev.updateStateOnServer('adapterSSID',statusDict['localNetwork']['stationMode']['SSID'])
					dev.updateStateOnServer('adapterRSSI',statusDict['localNetwork']['stationMode']['RSSI'])
					dev.updateStateOnServer('minCoolSetpoint',statusDict['userMinCoolSetPoint'])
					dev.updateStateOnServer('maxHeatSetpoint',statusDict['userMaxHeatSetPoint'])
			
	######################
	# Method to set the device's off timer
	# 
	def setOffTimerExpiration(self, pluginAction, dev):
		offTime = str(pluginAction.props.get("offTime"))
		dev.updateStateOnServer('offTime',offTime)
		self.logger.info("offTime for dev " + dev.name + "= " + offTime)



	
	######################
	# Method to check if the devices timer has experired so that it needs to be turned off
	# 
	def checkOffTimerExpiration(self, dev):
		now = datetime.datetime.today()		
		zeroTime = datetime.datetime.min
		zeroString = zeroTime.isoformat()+".000000"
		nowString = now.isoformat()
		
		offTime = datetime.datetime.strptime(dev.states["offTime"], "%Y-%m-%dT%H:%M:%S.%f")

		if not offTime == zeroTime:
			if now > offTime:
				self.logger.info("Timer expired for " + dev.name + " so turning unit off")
				dev.updateStateOnServer('offTime',zeroString)
				dev.updateStateOnServer('timeRemaining',' ')
				self._handleChangeHvacModeAction(dev, indigo.kHvacMode.Off)
			else:
				remainingTime = str((offTime -now).seconds/60+1)
				dev.updateStateOnServer('timeRemaining',remainingTime)
				
		
	
	######################
	# Method to expose the refreshStatesFromHardware to scripting
	# 
	def	refreshStatesFromHardware(self,pluginAction, dev):
		self._refreshStatesFromHardware(dev, True, True)



	######################
	# Poll all of the states from the thermostat and pass new values to
	# Indigo Server.
	def _refreshStatesFromHardware(self, dev, logRefresh, commJustStarted):
		self.unitCommunication(dev, "status", "")
#		if not dev.deviceTypeId == "mitsubishiHVACGroup":
#			# First Get the operating States			
#			jBody = json.dumps({"c":{"indoorUnit":{"status":{}}}})
#			stateOfUnit = self.sendMessageToHVAC(dev,jBody)
#			if stateOfUnit[0] == True :			
#				
#				statusDict = stateOfUnit[1]["r"]["indoorUnit"]["status"]
#				keyValueList = []
#				if statusDict['roomTemp'] != None:
#					dev.updateStateOnServer('displayUnitTemp',value=self.convertC2F(statusDict['roomTemp']))
#					dev.updateStateOnServer('displayFanSpeed',value=statusDict['fanSpeed'])
#					dev.updateStateOnServer('displayVaneDirection',value=statusDict['vaneDir'])
#					dev.updateStateOnServer('displaySetpointCool',value=self.convertC2F(statusDict['spCool']))
#					keyValueList.append({'key':'setpointHeat', 'value':self.convertC2F(statusDict['spCool'])})
#					dev.updateStateOnServer('displaySetpointHeat',value=self.convertC2F(statusDict['spHeat']))
#					keyValueList.append({'key':'setpointHeat', 'value':self.convertC2F(statusDict['spHeat'])})
#					dev.updateStateOnServer('displayHVACMode',value=statusDict['mode'])
#				
#
#					if statusDict['mode']=="heat": 
#						keyValueList.append({'key':'hvacOperationMode', 'value':indigo.kHvacMode.Heat})
#						dev.updateStateOnServer('displaySetpointTemp',value=self.convertC2F(statusDict["spHeat"]))
#					elif statusDict['mode']=="cool": 
#						keyValueList.append({'key':'hvacOperationMode', 'value':indigo.kHvacMode.Cool})
#						dev.updateStateOnServer('displaySetpointTemp',value=self.convertC2F(statusDict["spCool"]))
#					if len(keyValueList) > 0:
#						dev.updateStatesOnServer(keyValueList)
#				else:
#					self.logger.debug("bad value in statsDict: " + str(statusDict))
#				
#			# Next Get the Temp Sensor States States			
#			jBody = json.dumps({"c":{"sensors":{}}})
#			stateOfUnit = self.sendMessageToHVAC(dev,jBody)
#			if stateOfUnit[0] == True:
#				
#				statusDict = stateOfUnit[1]["r"]["sensors"]["0"]
#				dev.updateStateOnServer('sensorHumidity',value=statusDict['humidity'])
#				dev.updateStateOnServer('sensorRSSI',value=statusDict['rssi'])
#				dev.updateStateOnServer('sensorBatteryLevel',value=statusDict['battery'])
#			
#			# Next Get the WIFI Adaptor States States			
#			jBody = json.dumps({"c":{"adapter":{"status":{},"info":{}}}})
#			stateOfUnit = self.sendMessageToHVAC(dev,jBody)
#			if stateOfUnit[0] == True:
#				statusDict = stateOfUnit[1]["r"]["adapter"]["status"]
#				dev.updateStateOnServer('adapterSSID',value=statusDict['localNetwork']['stationMode']['SSID'])
#				dev.updateStateOnServer('adapterRSSI',value=statusDict['localNetwork']['stationMode']['RSSI'])
#				dev.updateStateOnServer('minCoolSetpoint',value=statusDict['userMinCoolSetPoint'])
#				dev.updateStateOnServer('maxHeatSetpoint',value=statusDict['userMaxHeatSetPoint'])
#
		
		
	######################
	# Process action request from Indigo Server to change the operating mode (Heat/Cool/Off)
	#
	def _handleChangeHvacModeAction(self, dev, newHvacMode):

		actionStr = _lookupActionStrFromHvacMode(newHvacMode)
		self.logger.info(actionStr)
		self.logger.info(newHvacMode)
		self.unitCommunication(dev,"mode", actionStr)
#		jBody = json.dumps({"c":{"indoorUnit":{"status":{"mode":actionStr}}}})
#		stateOfUnit = self.sendMessageToHVAC(dev,jBody)		
#		if stateOfUnit[0] == True:
#			statusDict = stateOfUnit[1]["r"]["indoorUnit"]["status"]
#			self.logger.info(u"sent \"%s\" mode change to %s" % (dev.name, actionStr))
#
#			# And then tell the Indigo Server to update the state.
#			if "hvacOperationMode" in dev.states:
#				dev.updateStateOnServer("hvacOperationMode", newHvacMode)
#				dev.updateStateOnServer('displayHVACMode',value=statusDict["mode"])
#		
#		else:
#			# Else log failure but do NOT update state on Indigo Server.
#			self.logger.info(u"send \"%s\" mode change to %s failed" % (dev.name, actionStr))





	######################
	# Process action request from Indigo Server to change a cool/heat setpoint.
	#
	def _handleChangeSetpointAction(self, dev, newSetpoint, logActionName, stateKey):		
		sendSuccess = False		# Set to False if it failed.
		if newSetpoint < 40.0:
			newSetpoint = 40.0		# Arbitrary -- set to whatever hardware minimum setpoint value is.
		elif newSetpoint > 95.0:
			newSetpoint = 95.0		# Arbitrary -- set to whatever hardware maximum setpoint value is.
		newSetpointC = self.convertF2Cish(newSetpoint) #Convert the Celcius (ish)
		if stateKey == u"setpointCool":
			self.unitCommunication(dev,"spCool", newSetpointC)
			
#			jBody = json.dumps({"c":{"indoorUnit":{"status":{"spCool":newSetpointC}}}})
#			stateOfUnit = self.sendMessageToHVAC(dev,jBody)
#			if stateOfUnit[0] == True:
#				sendSuccess = True
#				statusDict = stateOfUnit[1]["r"]["indoorUnit"]["status"]
#				if statusDict["spCool"] != None:					
#					dev.updateStateOnServer('displaySetpointCool',value=self.convertC2F(statusDict["spCool"]))
#					dev.updateStateOnServer('displaySetpointTemp',value=self.convertC2F(statusDict["spCool"]))
#				
			
		elif stateKey == u"setpointHeat":
			self.unitCommunication(dev,"spHeat", newSetpointC)
#			jBody = json.dumps({"c":{"indoorUnit":{"status":{"spHeat":newSetpointC}}}})
#			stateOfUnit = self.sendMessageToHVAC(dev,jBody)
#			if stateOfUnit[0] == True:
#				sendSuccess = True
#				statusDict = stateOfUnit[1]["r"]["indoorUnit"]["status"]
#				if statusDict["spHeat"] != None:
#					
#					dev.updateStateOnServer('displaySetpointHeat',value=self.convertC2F(statusDict["spHeat"]))
#					dev.updateStateOnServer('displaySetpointTemp',value=self.convertC2F(statusDict["spHeat"]))
#				

#		if sendSuccess == True:
#			# If success then log that the command was successfully sent.
#			self.logger.info(u"sent \"%s\" %s to %.1f°" % (dev.name, logActionName, newSetpoint))
#
#			# And then tell the Indigo Server to update the state.
#			if stateKey in dev.states:
#				dev.updateStateOnServer(stateKey, newSetpoint, uiValue="%.1f °F" % (newSetpoint))
#		else:
#			# Else log failure but do NOT update state on Indigo Server.
#			self.logger.info(u"send \"%s\" %s to %.1f° failed" % (dev.name, logActionName, newSetpoint))




	######################
	# Process action request from Indigo Server to change the vane direction on the unit
	# this is mitsubishi unit specific and not in the standard thermostat model
	#
	def setVaneDirection(self, pluginAction, dev):
		sendSuccess = False		# Set to False if it failed.
		newVaneDirection = str(pluginAction.props.get("vaneDirection"))
		self.unitCommunication(dev,"vaneDir", newVaneDirection)
#		self.logger.debug("setVaneDirection:  set vane Direction = " )
#		self.logger.debug(newVaneDirection)
#		jBody = json.dumps({"c":{"indoorUnit":{"status":{"vaneDir":newVaneDirection}}}})
#		stateOfUnit = self.sendMessageToHVAC(dev,jBody)
#		if stateOfUnit[0] == True:
#			sendSuccess = True
#			statusDict = stateOfUnit[1]["r"]["indoorUnit"]["status"]
#			dev.updateStateOnServer('displayVaneDirection',value=statusDict["vaneDir"])
#
#		if sendSuccess == True:
#			# If success then log that the command was successfully sent.
#			self.logger.info(u"Set the Vane Direction of HVAC Unit \"%s\"  to %s°" % (dev.name, newVaneDirection))
#
#		else:
#			# Else log failure but do NOT update state on Indigo Server.
#			self.logger.info(u"Failed to set the Vane Direction of HVAC Unit \"%s\"  to %s°" % (dev.name, newVaneDirection))
#			
			
			
			
			
	######################
	# Process action request from Indigo Server to change the fan speed on the unit
	# this is mitsubishi unit specific and not in the standard thermostat model
	#
	def setFanSpeed(self, pluginAction, dev):
		sendSuccess = False		# Set to False if it failed.
		newFanSpeed = str(pluginAction.props.get("fanSpeed"))
		self.unitCommunication(dev,"fanSpeed", newFanSpeed)
		
#		self.logger.debug("setFanSpeed: set fan speed = " )
#		self.logger.debug(newFanSpeed)
#		jBody = json.dumps({"c":{"indoorUnit":{"status":{"fanSpeed":newFanSpeed}}}})
#		stateOfUnit = self.sendMessageToHVAC(dev,jBody)
#		if stateOfUnit[0] == True:
#			sendSuccess = True
#			statusDict = stateOfUnit[1]["r"]["indoorUnit"]["status"]
#			dev.updateStateOnServer('displayFanSpeed',value=statusDict["fanSpeed"])
#
#		if sendSuccess == True:
#			# If success then log that the command was successfully sent.
#			self.logger.info(u"Set the Fan Speed of HVAC Unit \"%s\"  to %s°" % (dev.name, newFanSpeed))
#
#		else:
#			# Else log failure but do NOT update state on Indigo Server.
#			self.logger.info(u"Failed to set the Fan Speed of HVAC Unit \"%s\"  to %s°" % (dev.name, newFanSpeed))
#			


######################
# Process action request from Indigo Server to set the nighttime parameters on the unit
# this is mitsubishi unit specific and not in the standard thermostat model
#
	def setNightSettings(self,  pluginAction, dev):
		dev.updateStateOnServer("nightSet", value="True")
		dev.updateStateOnServer("nightFanSpeed", value=dev.states["displayFanSpeed"])
		dev.updateStateOnServer("nightVaneDirection", value=dev.states["displayVaneDirection"])
		dev.updateStateOnServer("nightHVACMode", value=dev.states["displayHVACMode"])
		dev.updateStateOnServer("nightSetpointTemp", value=dev.states["displaySetpointTemp"])
		dev.updateStateOnServer("nightSetpointHeat", value=dev.states["displaySetpointHeat"])
		dev.updateStateOnServer("nightSetpointCool", value=dev.states["displaySetpointCool"])
		

######################
# Process action request from Indigo Server to set the daytime parameters on the unit
# this is mitsubishi unit specific and not in the standard thermostat model
#
	def setDaySettings(self,  pluginAction, dev):
		dev.updateStateOnServer("daySet", value="True")
		dev.updateStateOnServer("dayFanSpeed", value=dev.states["displayFanSpeed"])
		dev.updateStateOnServer("dayVaneDirection", value=dev.states["displayVaneDirection"])
		dev.updateStateOnServer("dayHVACMode", value=dev.states["displayHVACMode"])
		dev.updateStateOnServer("daySetpointTemp", value=dev.states["displaySetpointTemp"])
		dev.updateStateOnServer("daySetpointHeat", value=dev.states["displaySetpointHeat"])
		dev.updateStateOnServer("daySetpointCool", value=dev.states["displaySetpointCool"])
		

	######################
	# Process action request from Indigo Server to change thermostat's fan mode.
	# NOT USED.  Just left this stub in the code
	def _handleChangeFanModeAction(self, dev, newFanMode):
		sendSuccess = True		# Set to False if it failed.
#
#		actionStr = _lookupActionStrFromFanMode(newFanMode)
#		if sendSuccess:
#			# If success then log that the command was successfully sent.
#			indigo.server.log(u"sent \"%s\" fan mode change to %s" % (dev.name, actionStr))
#
#			# And then tell the Indigo Server to update the state.
#			if "hvacFanMode" in dev.states:
#				dev.updateStateOnServer("hvacFanMode", newFanMode)
#		else:
#			# Else log failure but do NOT update state on Indigo Server.
#			indigo.server.log(u"send \"%s\" fan mode change to %s failed" % (dev.name, actionStr), isError=True)



##########################################################################
#Section:  Connection Status
# Utilities for managing the state "connectionStatus" for the HVAC units
#  connectionStatus initializes to 10, but then counts down each time a unit is unresponsive
#  Once it gets to 0, the unit will be treated as being disconnected and an error message is injected into the log file
#  If the unit responds one time, the connectionStatus is restored to 10
# 

	def restoreConnectionStatus(self, dev):
		# If conneciton fails 10 times, declare the unit unreachable.
		# When an unreachable unit is seen again, reset the connectionStatus to 10
		connectionStatus = dev.states['connectionStatus'] 
		if connectionStatus < 10:
			if connectionStatus == 0:
				self.logger.info("HVAC Unit " + str(dev.name) + " is reachable again")							
			connectionStatus = 10
		dev.updateStateOnServer('connectionStatus',value=connectionStatus)

	def reduceConnectionStatus (self, dev):
		# If conneciton fails 10 times, declare the unit unreachable.
		# When an unreachable unit is seen again, reset the connectionStatus to 10
		connectionStatus = dev.states['connectionStatus'] 
		if connectionStatus > 0:
			connectionStatus -= 1
			if connectionStatus == 0:
				self.logger.info("HVAC Unit " + str(dev.name) + " isn't reachable.  Check WiFi connection")					
		dev.updateStateOnServer('connectionStatus',value=connectionStatus)			



##########################################################################
#Section:  Groups
# HVAC units have states to indicate whih group they belong to
# There are also devices called groups which are basically just lists 
# of which units ae in that group

	##########################################################################
	#sub-Section:
	# First defind the callbacks for units that allows the group state information
	#  of the unit to be controlled by script


	
	#########################################
	# Groups allow units to be configured together
	#########################################
	def addUnitToGroup(self, pluginAction, dev):
		groupId = pluginAction.props.get(u"groupId")[0]
		groupName = pluginAction.props.get(u"groupName")

		self.logger.info("groupId = " + groupId +"groupName = "+groupName)
		dev.states[groupId] = groupName
		dev.updateStateOnServer(key=groupId, value=groupName)
		for device in indigo.devices:			
			if device.deviceTypeId =="mitsubishiHVACGroup" :
				device.updateStateOnServer("groupActive", value= False)	
		return()
		
	def removeUnitFromGroup(self, pluginAction, dev):
		groupId = pluginAction.props.get(u"groupId")[0]
		groupName = pluginAction.props.get(u"groupName")
		self.logger.info("groupId = " + groupId)
		if dev.states[groupId] == groupName:
			dev.states[groupId] ==""
			dev.updateStateOnServer(key=groupId, value="")
		for device in indigo.devices:			
			if device.deviceTypeId =="mitsubishiHVACGroup" :
				device.updateStateOnServer("groupActive", value= False)	
		
		return()

	def toggleGroupMembership(self, pluginAction, dev):
		groupId = pluginAction.props.get(u"groupId")[0]
		groupName = pluginAction.props.get(u"groupName")
		self.logger.info("toggleGroupMembership: groupID = " + str(groupId) + "groupName= " + str(groupName))
		if dev.states[groupId] == groupName:
			dev.states[groupId] ==""
			dev.updateStateOnServer(key=groupId, value="")
		else:
			dev.states[groupId] = groupName
			dev.updateStateOnServer(key=groupId, value=groupName)
		for device in indigo.devices:			
			if device.deviceTypeId =="mitsubishiHVACGroup" :
				device.updateStateOnServer("groupActive", value= False)	
		return()
		
	

	##########################################################################
	#Sub Section:
	#  Messaging to the HVAC Groups
	#  Although groups are essentially a UI concept, I have created a Group 
	#  Device because I needed to store and manage complex state information
	#	Regarding which unit was in which group
	#	Groups are configured when they are created in the New Device process
	#	but can be reconfigured at any time
	#   they are basically just a list of the dev id's of units that want to be 
	#   managed together.
	#   These utility methods activate and de-activate all of the units in the
	#   given group.   Activation basically only means setting the value of
	#   the "group3" state of the units (special group)
	##########################################################################

	######################
	# Process action request from Indigo Server to change the activation states
	# if activated -> deactivate      if deactivated -> activate
	#
	def toggleGroupMembersActive(self, pluginAction, dev):
		isGroupActive = dev.states["groupActive"]
		if isGroupActive:
			self.setGroupMembersInactive(pluginAction, dev)
			self.logger.info("set group state of " + str(dev.name) + " to Inactive")
			
		else:
			self.setGroupMembersActive(pluginAction, dev)
			self.logger.info("set group state of " + str(dev.name) + " to Active")
	######################
	# Process action request from Indigo Server to change the activation states
	# activate all of the units in the group and de-activate units not in the group
	#			
	def setGroupMembersActive(self, pluginAction, dev):
		deviceIdList = dev.ownerProps.get("groupMembers")
		for device in indigo.devices:			
			if device.deviceTypeId =="mitsubishiHVACDuctless" :
				groupName = "Active" if str(device.id) in deviceIdList else ""
				device.updateStateOnServer('group3',value=groupName)		
		for device in indigo.devices:			
			if device.deviceTypeId =="mitsubishiHVACGroup" :
				device.updateStateOnServer("groupActive", value= False)	
		dev.updateStateOnServer("groupActive", value= True)

	######################
	# Process action request from Indigo Server to change the activation states
	# deactivate all of the units in the group 
	#	
	def setGroupMembersInactive(self, pluginAction, dev):
		deviceIdList = dev.ownerProps.get("groupMembers")
		for device in indigo.devices:			
			if device.deviceTypeId =="mitsubishiHVACDuctless" :
				if str(device.id) in deviceIdList:
					device.updateStateOnServer('group3',value="")					
		for device in indigo.devices:			
			if device.deviceTypeId =="mitsubishiHVACGroup" :
				device.updateStateOnServer("groupActive", value= False)	
			
	######################
	# Process action request from Indigo Server to change the activation states
	# deactivate all of the units (regardless of what group they are associated with)
	# and then set all of the groups themselves to the "deactivated" state 
	#	
	def setAllInactive(self, pluginAction, dev):
		for device in indigo.devices:			
			if device.deviceTypeId =="mitsubishiHVACDuctless" :
				device.updateStateOnServer('group3',value="");
		for device in indigo.devices:			
			if device.deviceTypeId =="mitsubishiHVACGroup" :
				device.updateStateOnServer("groupActive", value= False)	





			
	########################################
	def startup(self):
		self.debugLog(u"startup called")

	def shutdown(self):
		self.debugLog(u"shutdown called")

	########################################
	def runConcurrentThread(self):
		try:
			while True:
				for dev in indigo.devices.iter("self"):
					if not dev.deviceTypeId == "mitsubishiHVACGroup":
						if not dev.enabled or not dev.configured:
								continue

					# Plugins that need to poll out the status from the thermostat
					# could do so here, then broadcast back the new values to the
					# Indigo Server.
						self.checkOffTimerExpiration(dev)
						self._refreshStatesFromHardware(dev, False, False)

				self.sleep(self.refreshDelay)
		except self.StopThread:
			pass	# Optionally catch the StopThread exception and do any needed cleanup.

	########################################
#	def validateDeviceConfigUi(self, valuesDict, typeId, devId):
#		
#		return (True, valuesDict)

	########################################
	#def deviceStartComm(self, dev):
	# Called when communication with the hardware should be established.
	# Here would be a good place to poll out the current states from the
	# thermostat. If periodic polling of the thermostat is needed (that
	# is, it doesn't broadcast changes back to the plugin somehow), then
	# consider adding that to runConcurrentThread() above.
	def deviceStartComm(self, dev):
		self.logger.info("deviceStartComm " + dev.name )
		dev.stateListOrDisplayStateIdChanged()
		if not dev.deviceTypeId == "mitsubishiHVACGroup":
			#Initialize the off timer to it's disabled state
			zeroTime = datetime.datetime.min
			zeroString = zeroTime.isoformat()+".000000"
			dev.updateStateOnServer('offTime',zeroString)
			dev.updateStateOnServer('timeRemaining', " ")
		self._refreshStatesFromHardware(dev, True, True)
		return

	def deviceStopComm(self, dev):
		# Called when communication with the hardware should be shutdown.
		pass

	########################################
	# Thermostat Action callback
	######################
	# Main thermostat action bottleneck called by Indigo Server.
	def actionControlThermostat(self, action, dev):
		###### SET HVAC MODE ######
		if action.thermostatAction == indigo.kThermostatAction.SetHvacMode:
			self._handleChangeHvacModeAction(dev, action.actionMode)
			
			#self.unitCommunication( dev, action.actionMode, action.actionValue)
		###### SET FAN MODE ######
		elif action.thermostatAction == indigo.kThermostatAction.SetFanMode:
			self._handleChangeFanModeAction(dev, action.actionMode)

		###### SET COOL SETPOINT ######
		elif action.thermostatAction == indigo.kThermostatAction.SetCoolSetpoint:
			newSetpoint = action.actionValue
			self._handleChangeSetpointAction(dev, newSetpoint, u"change cool setpoint", u"setpointCool")

		###### SET HEAT SETPOINT ######
		elif action.thermostatAction == indigo.kThermostatAction.SetHeatSetpoint:
			newSetpoint = action.actionValue
			self._handleChangeSetpointAction(dev, newSetpoint, u"change heat setpoint", u"setpointHeat")

		###### DECREASE/INCREASE COOL SETPOINT ######
		elif action.thermostatAction == indigo.kThermostatAction.DecreaseCoolSetpoint:
			newSetpoint = dev.coolSetpoint - action.actionValue
			self._handleChangeSetpointAction(dev, newSetpoint, u"decrease cool setpoint", u"setpointCool")

		elif action.thermostatAction == indigo.kThermostatAction.IncreaseCoolSetpoint:
			newSetpoint = dev.coolSetpoint + action.actionValue
			self._handleChangeSetpointAction(dev, newSetpoint, u"increase cool setpoint", u"setpointCool")

		###### DECREASE/INCREASE HEAT SETPOINT ######
		elif action.thermostatAction == indigo.kThermostatAction.DecreaseHeatSetpoint:
			newSetpoint = dev.heatSetpoint - action.actionValue
			self._handleChangeSetpointAction(dev, newSetpoint, u"decrease heat setpoint", u"setpointHeat")

		elif action.thermostatAction == indigo.kThermostatAction.IncreaseHeatSetpoint:
			newSetpoint = dev.heatSetpoint + action.actionValue
			self._handleChangeSetpointAction(dev, newSetpoint, u"increase heat setpoint", u"setpointHeat")

		###### REQUEST STATE UPDATES ######
		elif action.thermostatAction in [indigo.kThermostatAction.RequestStatusAll, indigo.kThermostatAction.RequestMode, indigo.kThermostatAction.RequestEquipmentState, indigo.kThermostatAction.RequestTemperatures, indigo.kThermostatAction.RequestHumidities,indigo.kThermostatAction.RequestDeadbands, indigo.kThermostatAction.RequestSetpoints]:
			self._refreshStatesFromHardware(dev, True, False)
			

	########################################
	# General Action callback
	######################
	def actionControlUniversal(self, action, dev):
		###### BEEP ######
		if action.deviceAction == indigo.kUniversalAction.Beep:
			# Beep the hardware module (dev) here:
			# ** IMPLEMENT ME **
			indigo.server.log(u"sent \"%s\" %s" % (dev.name, "beep request"))

		###### ENERGY UPDATE ######
		elif action.deviceAction == indigo.kUniversalAction.EnergyUpdate:
			# Request hardware module (dev) for its most recent meter data here:
			# ** IMPLEMENT ME **
			indigo.server.log(u"sent \"%s\" %s" % (dev.name, "energy update request"))

		###### ENERGY RESET ######
		elif action.deviceAction == indigo.kUniversalAction.EnergyReset:
			# Request that the hardware module (dev) reset its accumulative energy usage data here:
			# ** IMPLEMENT ME **
			indigo.server.log(u"sent \"%s\" %s" % (dev.name, "energy reset request"))

		###### STATUS REQUEST ######
		elif action.deviceAction == indigo.kUniversalAction.RequestStatus:
			# Query hardware module (dev) for its current status here. This differs from the 
			# indigo.kThermostatAction.RequestStatusAll action - for instance, if your thermo
			# is battery powered you might only want to update it only when the user uses
			# this status request (and not from the RequestStatusAll). This action would
			# get all possible information from the thermostat and the other call
			# would only get thermostat-specific information:
			# ** GET BATTERY INFO **
			# and call the common function to update the thermo-specific data
			self._refreshStatesFromHardware(dev, True, False)
			indigo.server.log(u"sent \"%s\" %s" % (dev.name, "status request"))


	########################################
	# Internal utility methods. Some of these are useful to provide
	# a higher-level abstraction for accessing/changing thermostat
	# properties or states.
	######################
	def _changeTempSensorCount(self, dev, count):
		newProps = dev.pluginProps
		newProps["NumTemperatureInputs"] = count
		dev.replacePluginPropsOnServer(newProps)

	def _changeHumiditySensorCount(self, dev, count):
		newProps = dev.pluginProps
		newProps["NumHumidityInputs"] = count
		dev.replacePluginPropsOnServer(newProps)

	def _changeAllTempSensorCounts(self, count):
		for dev in indigo.devices.iter("self"):
			self._changeTempSensorCount(dev, count)

	def _changeAllHumiditySensorCounts(self, count):
		for dev in indigo.devices.iter("self"):
			self._changeHumiditySensorCount(dev, count)

	######################
	def _changeTempSensorValue(self, dev, index, value, keyValueList):
		# Update the temperature value at index. If index is greater than the "NumTemperatureInputs"
		# an error will be displayed in the Event Log "temperature index out-of-range"
		stateKey = u"temperatureInput" + str(index)
		keyValueList.append({'key':stateKey, 'value':value, 'uiValue':"%d °F" % (value)})
		self.debugLog(u"\"%s\" updating %s %d" % (dev.name, stateKey, value))

	def _changeHumiditySensorValue(self, dev, index, value, keyValueList):
		# Update the humidity value at index. If index is greater than the "NumHumidityInputs"
		# an error will be displayed in the Event Log "humidity index out-of-range"
		stateKey = u"humidityInput" + str(index)
		keyValueList.append({'key':stateKey, 'value':value, 'uiValue':"%d °F" % (value)})
		self.debugLog(u"\"%s\" updating %s %d" % (dev.name, stateKey, value))



	

	########################################
	# Custom Plugin Action callbacks (defined in Actions.xml)
	######################
	def setBacklightBrightness(self, pluginAction, dev):
		try:
			newBrightness = int(pluginAction.props.get(u"brightness", 100))
		except ValueError:
			# The int() cast above might fail if the user didn't enter a number:
			indigo.server.log(u"set backlight brightness action to device \"%s\" -- invalid brightness value" % (dev.name,), isError=True)
			return

		# Command hardware module (dev) to set backlight brightness here:
		# ** IMPLEMENT ME **
		sendSuccess = True		# Set to False if it failed.

		if sendSuccess:
			# If success then log that the command was successfully sent.
			indigo.server.log(u"sent \"%s\" %s to %d" % (dev.name, "set backlight brightness", newBrightness))

			# And then tell the Indigo Server to update the state:
			dev.updateStateOnServer("backlightBrightness", newBrightness, uiValue="%d%%" % (newBrightness))
		else:
			# Else log failure but do NOT update state on Indigo Server.
			indigo.server.log(u"send \"%s\" %s to %d failed" % (dev.name, "set backlight brightness", newBrightness), isError=True)

	########################################
	# Actions defined in MenuItems.xml. In this case we just use these menu actions to
	# simulate different thermostat configurations (how many temperature and humidity
	# sensors they have).
	####################
	def changeTempSensorCountTo1(self):
		self._changeAllTempSensorCounts(1)

	def changeTempSensorCountTo2(self):
		self._changeAllTempSensorCounts(2)

	def changeTempSensorCountTo3(self):
		self._changeAllTempSensorCounts(3)

	def changeHumiditySensorCountTo0(self):
		self._changeAllHumiditySensorCounts(0)

	def changeHumiditySensorCountTo1(self):
		self._changeAllHumiditySensorCounts(1)

	def changeHumiditySensorCountTo2(self):
		self._changeAllHumiditySensorCounts(2)

	def changeHumiditySensorCountTo3(self):
		self._changeAllHumiditySensorCounts(3)

		