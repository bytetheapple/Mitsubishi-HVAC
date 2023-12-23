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
import math



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
		self.refreshDelay = 15				# seconds between hardware state refreshes
		self.thermostatPeriod = 6			# How many refresh cycles between thermostat cycles
		self.groupTempOffset = 3				# Number of degrees past the desired setpoint that each unit in a group is set to in order ot ensure they actually stay on
		self.debugEnabled = False			# Can be set to True in the Config UI
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
	######################################
	# Dynamically enable error logging
	######################################
	def EnableDebug(self, valuesDict):#, typeId, devId): #, typeId, devId):
		# do whatever you need to here
		self.debug =  valuesDict['debugEnabled']
		return(valuesDict)
	
	
	
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
			returnValue = (32+(float(cTemp)*1.8))
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

	#################
	# File Utilities
	#################
	

	def recoverStatesFromDisk(self,dev):
		results = self.recoverDataFromDisk("statesForDev_"+str(dev.id))
		if results["success"]:
			results["data"] = json.loads(results["data"])
		return(results)



	def recoverDataFromDisk(self, fileName):
		returnDict = {"success":False, "data":""}
		pluginConfigFolder = indigo.server.getInstallFolderPath() + "/Preferences/Plugins/" 
		if os.path.isdir(pluginConfigFolder):
			configDir = pluginConfigFolder + self.pluginId
			if os.path.isfile(configDir+"/"+fileName):
				f = open(configDir+"/"+fileName, "r")
				returnDict["data"] = f.read()
				f.close()
				returnDict["success"] = True
		else:
			returnDict["success"] = False			
		return(returnDict)

	
	
	
	
	def saveStatesToDisk(self, dev, keyValueList):
		recoveredData = self.recoverStatesFromDisk(dev)
		if recoveredData["success"]:
			updatedStates = recoveredData["data"]
		else:
			updatedStates = {}
		for item in keyValueList:
			updatedStates[item["key"]] = item["value"]
#			if item["key"] in updatedStates:
#				updatedStates[key] = item["value"]
#			else:
#				updatedStates.append({item['key']: item['value']})
		dataToSave = json.dumps(updatedStates)
		success = self.saveDataToDisk("statesForDev_"+str(dev.id), dataToSave)
		return(success)
		

		
	def saveDataToDisk(self, fileName, data):
		success = False
		pluginConfigFolder = indigo.server.getInstallFolderPath() + "/Preferences/Plugins/" 
		if os.path.isdir(pluginConfigFolder):
			configDir = pluginConfigFolder + self.pluginId
			
			if not os.path.isdir(configDir):
				os.mkdir(configDir)
				self.logger.info("created Directory: "+configDir)
				
			f = open(configDir+"/"+fileName, "w+")
			f.write(data)
			f.close
			success = True
		return(success)
		
		
		
		
		
		
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
		#self.logger.debug(body)
		success = False
		responseDirectory = {}
		#self.logger.debug("Sending message to address: "+ address)
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
						#self.logger.debug(responseDirectory)
					else:
						self.logger.debug("Bad response from unit " + address + "  Response received: "+str(theResponse))
					self.restoreConnectionStatus(dev)	
					break
				
			self.logger.debug("Retrying message to address: "+ address + "unit: " + name + " times= " + str(retryTimes) )
		
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
				self.logger.debug(u"Sending %s command to %s with setting \"%s\" " % (action, dev.name, actionValue))
			jBody = json.dumps({"c":{"indoorUnit":{"status":commandEntry}}})
			stateOfUnit = self.sendMessageToHVAC(dev,jBody)
			if stateOfUnit[0] == True :	
				if action != "status":
					self.logger.debug(u"Command %s \"%s\" successfully sent to %s " % (action, actionValue, dev.name))							
				statusDict = stateOfUnit[1]["r"]["indoorUnit"]["status"]
				if "roomTemp" in statusDict:
					if statusDict['roomTemp'] != None:
						dev.updateStateOnServer('displayUnitTemp',value=self.convertC2F(statusDict['roomTemp']), decimalPlaces=0)
						
				if "fanSpeed" in statusDict:
					dev.updateStateOnServer('displayFanSpeed',value=statusDict['fanSpeed'])
					
				if "vaneDir" in statusDict:
					dev.updateStateOnServer('displayVaneDirection',value=statusDict['vaneDir'])
					
				if "spCool" in statusDict:
					if statusDict['spCool'] != None:
						dev.updateStateOnServer('displaySetpointCool',self.convertC2F(statusDict['spCool']), decimalPlaces = 0)
						dev.updateStateOnServer('setpointCool', self.convertC2F(statusDict['spCool']), decimalPlaces = 0)
						dev.updateStateOnServer('displaySetpointTemp',self.convertC2F(statusDict["spCool"]), decimalPlaces = 0)
						#dev.updateStateOnServer('displaySetpointTemp',self.convertC2F(statusDict["spCool"]))					
					
				if "spHeat" in statusDict:
					if statusDict['spHeat'] != None:
						dev.updateStateOnServer('displaySetpointHeat',self.convertC2F(statusDict['spHeat']), decimalPlaces = 0)
						dev.updateStateOnServer('setpointHeat', self.convertC2F(statusDict['spHeat']), decimalPlaces = 0)
						dev.updateStateOnServer('displaySetpointTemp',self.convertC2F(statusDict["spHeat"]), decimalPlaces = 0)
						#dev.updateStateOnServer('displaySetpointTemp',self.convertC2F(statusDict["spHeat"]))
					
				if "mode" in statusDict:
					dev.updateStateOnServer('displayHVACMode',statusDict['mode'])
					if statusDict['mode']=="heat": 
						dev.updateStateOnServer('hvacOperationMode', indigo.kHvacMode.Heat)
						if "spHeat" in statusDict:
							if statusDict['spHeat'] != None:
								dev.updateStateOnServer('displaySetpointTemp',self.convertC2F(statusDict["spHeat"]), decimalPlaces = 0)
								dev.updateStateOnServer('setpointHeat', self.convertC2F(statusDict['spHeat']), decimalPlaces = 0)
					elif statusDict['mode']=="cool": 							
						dev.updateStateOnServer('hvacOperationMode', indigo.kHvacMode.Cool)
						if "spCool" in statusDict:
							if statusDict['spCool'] != None:
								dev.updateStateOnServer('displaySetpointTemp',self.convertC2F(statusDict["spCool"]), decimalPlaces = 0)
								dev.updateStateOnServer('setpointCool', self.convertC2F(statusDict['spCool']), decimalPlaces = 0)
					elif statusDict['mode']=="off": 							
						dev.updateStateOnServer('hvacOperationMode', indigo.kHvacMode.Off)
														
			else:
				if action != "status":
					self.logger.debug(u"Command %s \"%s\" failed to send to %s " % (action, actionValue, dev.name))
				
			if action == "status":
				# Next Get the Temp Sensor States States			
				jBody = json.dumps({"c":{"sensors":{}}})
				stateOfUnit = self.sendMessageToHVAC(dev,jBody)
				if stateOfUnit[0] == True:
					
					statusDict = stateOfUnit[1]["r"]["sensors"]["0"]
					dev.updateStateOnServer('sensorHumidity',statusDict['humidity'], decimalPlaces = 0)
					dev.updateStateOnServer('sensorRSSI',statusDict['rssi'], decimalPlaces = 0)
					if dev.pluginProps['externalTempSensor']:					
						if str(statusDict['rssi']) == "None":
							dev.updateStateOnServer('sensorLost', True)
						else:
							dev.updateStateOnServer('sensorLost', False)
					dev.updateStateOnServer('sensorBatteryLevel',statusDict['battery'], decimalPlaces = 0)
				
				# Next Get the WIFI Adaptor States States			
				jBody = json.dumps({"c":{"adapter":{"status":{},"info":{}}}})
				stateOfUnit = self.sendMessageToHVAC(dev,jBody)
				if stateOfUnit[0] == True:
					statusDict = stateOfUnit[1]["r"]["adapter"]["status"]
					dev.updateStateOnServer('adapterSSID',statusDict['localNetwork']['stationMode']['SSID'])
					dev.updateStateOnServer('adapterRSSI',statusDict['localNetwork']['stationMode']['RSSI'])
					dev.updateStateOnServer('minCoolSetpoint',statusDict['userMinCoolSetPoint'])
					dev.updateStateOnServer('maxHeatSetpoint',statusDict['userMaxHeatSetPoint'])
				# Next Get the Indoor Unit States States			
				jBody = json.dumps({"c":{"indoorUnit":{"status":{}}}})
				stateOfUnit = self.sendMessageToHVAC(dev,jBody)
				if stateOfUnit[0] == True:
					statusDict = stateOfUnit[1]["r"]["indoorUnit"]["status"]	
					if "roomTemp" in statusDict:
						if statusDict['roomTemp'] != None:
							dev.updateStateOnServer(key="temperatureInput1", value= self.convertC2F(statusDict['roomTemp']), decimalPlaces = 0)
			
	######################
	# Method to set the device's off timer
	# 
	def setOffTimerExpiration(self, pluginAction, dev):
		offTime = str(pluginAction.props.get("offTime"))
		dev.updateStateOnServer('offTime',offTime)
		self.logger.debug("offTime for dev " + dev.name + "= " + offTime)



	
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
				self.logger.debug("Timer expired for " + dev.name + " so turning unit off")
				dev.updateStateOnServer('offTime',zeroString)
				dev.updateStateOnServer('timeRemaining',' ')
				#action = {"thermostatAction":indigo.kThermostatAction.SetHvacMode, "description":"Timer Expired - turn unit off", "actionMode":indigo.kHvacMode.Off}
				indigo.thermostat.setHvacMode(dev, value=indigo.kHvacMode.Off)
				#self.actionControlThermostat(action, dev)
				#self._handleChangeHvacModeAction(dev, indigo.kHvacMode.Off)
			else:
				remainingTime = str((offTime -now).seconds/60+1)
				dev.updateStateOnServer('timeRemaining',remainingTime)
				
		
	
	######################
	# Method to expose the refreshStatesFromHardware to scripting
	# 
	def	refreshStatesFromHardware(self,pluginAction, dev):
		if dev.deviceTypeId == "mitsubishiHVACGroup":
				self._refreshStatesFromUnits(dev)
		else:
			self._refreshStatesFromHardware(dev, True, True)



	######################
	# Poll all of the states from the thermostat and pass new values to
	# Indigo Server.
	def _refreshStatesFromHardware(self, dev, logRefresh, commJustStarted):
		self.unitCommunication(dev, "status", "")
		
		
	######################
	# Process action request from Indigo Server to change the operating mode (Heat/Cool/Off)
	#
	def _handleChangeHvacModeAction(self, dev, newHvacMode):

		actionStr = _lookupActionStrFromHvacMode(newHvacMode)
		self.unitCommunication(dev,"mode", actionStr)





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
			
				
			
		elif stateKey == u"setpointHeat":
			self.unitCommunication(dev,"spHeat", newSetpointC)



	######################
	# Process action request from Indigo Server to change the vane direction on the unit
	# this is mitsubishi unit specific and not in the standard thermostat model
	#
	def setVaneDirection(self, pluginAction, dev):
		sendSuccess = False		# Set to False if it failed.
		newVaneDirection = str(pluginAction.props.get("vaneDirection"))
		self.unitCommunication(dev,"vaneDir", newVaneDirection)
			
			
			
			
	######################
	# Process action request from Indigo Server to change the fan speed on the unit
	# this is mitsubishi unit specific and not in the standard thermostat model
	#
	def setFanSpeed(self, pluginAction, dev):
		sendSuccess = False		# Set to False if it failed.
		newFanSpeed = str(pluginAction.props.get("fanSpeed"))
		self.unitCommunication(dev,"fanSpeed", newFanSpeed)
		



	######################
	# Process action request from Indigo Server to change thermostat's fan mode.
	# NOT USED.  Just left this stub in the code
	def _handleChangeFanModeAction(self, dev, newFanMode):
		sendSuccess = True		# Set to False if it failed.


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
		dev.updateStateOnServer('connectionLost',value=False)
		dev.updateStateOnServer('connectionStatus',value=connectionStatus)

	def reduceConnectionStatus (self, dev):
		# If conneciton fails 10 times, declare the unit unreachable.
		# When an unreachable unit is seen again, reset the connectionStatus to 10
		connectionStatus = dev.states['connectionStatus'] 
		if connectionStatus > 0:
			connectionStatus -= 1
			if connectionStatus == 0:
				self.logger.info("HVAC Unit " + str(dev.name) + " isn't reachable.  Check WiFi connection")	
				dev.updateStateOnServer('connectionLost',value=True)
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

			dev.updateStateOnServer(key=groupId, value="")
		else:

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

	def setAllInactive(self, pluginAction, dev):
		self.logger.info("Hello World")
		

	
	
	

	
	
		
	def _refreshStatesFromUnits(self, dev):
		if dev.deviceTypeId == "mitsubishiHVACGroup":
			# Update Temperature and Humidity
			sumOfTemps = 0
			sumOfHumidity = 0
			sumOfRemoteTemps = 0
			sumOfRemoteHumidity = 0
			numOfSensors = 0
			numOfRemoteSensors = 0
			unitsWithRemoteSensors = 0
			numOfUnits = 0
			numOfDisconnectedUnits = 0
			connectionStatus = 10
			batteryLevel = 100
			deviceIdList = dev.ownerProps.get("groupMembers")
			for tmpDev in indigo.devices.iter("self.mitsubishiHVACDuctless"):
				
				if str(tmpDev.id) in deviceIdList:   #Device is in the group
					numOfUnits +=1
					numOfDisconnectedUnits += 1 if tmpDev.states["connectionStatus"]==0 else 0
					if tmpDev.states["connectionStatus"] < connectionStatus:
						connectionStatus = tmpDev.states["connectionStatus"]
					sensorBatteryLevel = tmpDev.states["sensorBatteryLevel"]
					if  sensorBatteryLevel != "" and int(sensorBatteryLevel) < batteryLevel:
						batteryLevel = int(sensorBatteryLevel)  # Set the sensor battery level to the lowest level of any sensor in the group
#					self.logger.info("Refreshing Group \"%s device: \"%s Current Temp:\"%s  Current Humidity:\" %s Sensor RSSI: \"%s" % (dev.name, tmpDev.name, tmpDev.states["temperatureInput1"], tmpDev.states["sensorHumidity"], tmpDev.states["sensorRSSI"]) )
					
					# For Groups that don't have any remote Sensors
					sumOfTemps += float(tmpDev.states["temperatureInput1"])
					#sumOfHumidity += float(tmpDev.states["sensorHumidity"])
					numOfSensors += 1
				
					
					#For Groups that do have remote sensors
					if  tmpDev.states["sensorRSSI"] != "":
						sumOfRemoteTemps += float(tmpDev.states["temperatureInput1"])
						sumOfRemoteHumidity += float(tmpDev.states["sensorHumidity"])
						numOfRemoteSensors += 1
					if tmpDev.pluginProps['externalTempSensor']:
						unitsWithRemoteSensors +=1
			
			keyValueList = []
			keyValueList.append({'key':'connectionStatus', 'value':connectionStatus})# If Connection status of any unit is equal to 0 then set this to 0 (disconnected)		
			
			if numOfRemoteSensors > 0:
				aveTemp = sumOfRemoteTemps / numOfRemoteSensors
				aveHumidity = sumOfRemoteHumidity / numOfRemoteSensors
			else: #no units with remote temp sensors in this group
				aveTemp = sumOfTemps / numOfSensors
				aveHumidity = 0
				if dev.ownerProps.get("groupExternalTempSensor") and not dev.ownerProps.get("externalTempSensorDevId") == None: #all remote temp sensors are MIA and there is a backup
					myExternalTempSensor = dev.ownerProps.get("externalTempSensorDevId")
					for tempSensor in indigo.devices.iter("indigo.sensor"):						
						if str(tempSensor.id) == myExternalTempSensor:
							#self.logger.info("All of external sensors are missing form %s so using  %s as a backup which is reporting %s" % (dev.name, tempSensor.name, str(tempSensor.states["sensorTemp"])))
							aveTemp = tempSensor.states["sensorTemp"]
							
							

			keyValueList.append({'key':'numOfDisconnectedUnits', 'value':numOfDisconnectedUnits})	
			keyValueList.append({'key':'sensorBatteryLevel', 'value':sensorBatteryLevel})
			keyValueList.append({'key':'temperatureInput1', 'value':aveTemp, 'decimalPlaces':0})
			keyValueList.append({'key':'displayUnitTemp', 'value':aveTemp, 'decimalPlaces':0})
			keyValueList.append({'key':'sensorHumidity', 'value':aveHumidity, 'decimalPlaces':0})
			keyValueList.append({'key':'displayUnitHumidity', 'value':aveHumidity, 'decimalPlaces':0})
							
			missingSensor = (numOfRemoteSensors < numOfUnits)
			keyValueList.append({'key':"missingTempSensor", 'value':missingSensor})
			keyValueList.append({'key':"missingTempSensorCount", 'value':unitsWithRemoteSensors - numOfRemoteSensors})
				
			for tmpDev in indigo.devices.iter("self.mitsubishiHVACDuctless"):
				for stateLabel in ["displayFanSpeed","displayVaneDirection"]:
					if stateLabel in keyValueList:
						keyValueList[stateLabel]
					else:
						keyValueList.append({'key':stateLabel, 'value':tmpDev.states[stateLabel]})
					
			dev.updateStatesOnServer(keyValueList)
			self.saveStatesToDisk(dev, keyValueList)
	



	######################
	# Virtual Group Thermostat
	# Will 
	#	-check to make sure that all units in the group are in the same mode
	#	- Average the temp for all units that have a wireless temp sensor
	# deactivate all of the units (regardless of what group they are associated with)
	# and then set all of the groups themselves to the "deactivated" state 
	#	
	
	def groupTemperatureControl(self,dev):
		if dev.deviceTypeId == "mitsubishiHVACGroup":
			if dev.ownerProps.get("groupAutomatedTempControl"):
				devMode = dev.states["hvacOperationMode"]
				devSpHeat = float(dev.states["setpointHeat"])
				devSpCool = float(dev.states["setpointCool"])
				devCurrentTemp = float(dev.states["temperatureInput1"])
				deviceIdList = dev.ownerProps.get("groupMembers")
				now = datetime.datetime.today()		
				nowString = now.isoformat()
				offTime = datetime.datetime.strptime(dev.states["tempControlOffTime"], "%Y-%m-%dT%H:%M:%S.%f")
				onTime = datetime.datetime.strptime(dev.states["tempControlOnTime"], "%Y-%m-%dT%H:%M:%S.%f")
				onPeriod = offTime-onTime
				offPeriod = onTime-offTime
				
				for tmpDev in indigo.devices.iter("self.mitsubishiHVACDuctless"):
					if str(tmpDev.id) in deviceIdList:   #Device is in the group
						if tmpDev.states["connectionStatus"]>0: # Don't bother if the unit isn't listening
							if devMode == indigo.kHvacMode.Heat:
								if devCurrentTemp < devSpHeat and tmpDev.states["hvacOperationMode"] == indigo.kHvacMode.Off:
									#Turn the units on becauce the temp is low
									offPeriod = now - offTime
									onPeriod = offTime- onTime
									self.calcAve(dev, onPeriod, offPeriod)									
									dev.updateStateOnServer("tempControlOnTime", nowString)
									dev.updateStateOnServer("tempControlIsOn", True)
									self._handleChangeHvacModeAction(tmpDev, indigo.kHvacMode.Heat)
									newSetPoint = devSpHeat+self.groupTempOffset
									self._handleChangeSetpointAction(tmpDev, newSetPoint, u"change heat setpoint", u"setpointHeat")
									self.logger.info("Adjusting Group \"%s device: \"%s Current Temp:\"%s  turning the heat up to  \"%s" % (dev.name, tmpDev.name, dev.states["temperatureInput1"], str(newSetPoint)) )
									
									
								elif devCurrentTemp > devSpHeat and tmpDev.states["hvacOperationMode"] == indigo.kHvacMode.Heat:
									#Turn the unit off becasue the temp is right
									offPeriod = onTime - offTime
									onPeriod = now - onTime
									self.calcAve(dev, onPeriod, offPeriod)
									dev.updateStateOnServer("tempControlOffTime", nowString)
									dev.updateStateOnServer("tempControlIsOn", False)
									self._handleChangeHvacModeAction(tmpDev, indigo.kHvacMode.Off)
									self.logger.info("Adjusting Group \"%s device: \"%s Current Temp:\"%s  turning off the heat ." % (dev.name, tmpDev.name, dev.states["temperatureInput1"]) )
		
							elif devMode == indigo.kHvacMode.Cool:
								if devCurrentTemp > devSpCool and tmpDev.states["hvacOperationMode"] == indigo.kHvacMode.Off:
									#Turn the units on becauce the temp is high
									offPeriod = now - offTime
									onPeriod = offTime- onTime
									self.calcAve(dev, onPeriod, offPeriod)
									dev.updateStateOnServer("tempControlOnTime", nowString)
									dev.updateStateOnServer("tempControlIsOn", True)
									self._handleChangeHvacModeAction(tmpDev, indigo.kHvacMode.Cool)
									newSetPoint = devSpCool-self.groupTempOffset 
									self._handleChangeSetpointAction(tmpDev, newSetPoint, u"change cool setpoint", u"setpointCool")
									self.logger.info("Adjusting Group \"%s device: \"%s Current Temp:\"%s  turning cool down to  \"%s" % (dev.name, tmpDev.name, dev.states["temperatureInput1"], str(newSetPoint)) )
									
								elif devCurrentTemp < devSpCool and tmpDev.states["hvacOperationMode"] == indigo.kHvacMode.Cool:
									#Turn the unit off becasue the temp is right
									offPeriod = onTime - offTime
									onPeriod = now - onTime
									self.calcAve(dev, onPeriod, offPeriod)
									dev.updateStateOnServer("tempControloffTime", nowString)
									dev.updateStateOnServer("tempControlIsOn", False)
									self._handleChangeHvacModeAction(tmpDev, indigo.kHvacMode.Off)
									self.logger.info("Adjusting Group \"%s device: \"%s Current Temp:\"%s  turning off the cool" % (dev.name, tmpDev.name, dev.states["temperatureInput1"]) )
			
							elif devMode == indigo.kHvacMode.Off:
								if not tmpDev.states["hvacOperationMode"] == indigo.kHvacMode.Off:
									#Turn the unit off becasue Mode is Off
									offPeriod = onTime - offTime
									onPeriod = now - onTime
									self.calcAve(dev, onPeriod, offPeriod)
									dev.updateStateOnServer("tempControlOffTime", nowString)
									dev.updateStateOnServer("tempControlIsOn", False)
									self._handleChangeHvacModeAction(tmpDev, indigo.kHvacMode.Off)
									self.logger.info("Mode Off - Adjusting Group \"%s device: \"%s Current Temp:\"%s  turning off the heat ." % (dev.name, tmpDev.name, dev.states["temperatureInput1"]) )
							

	def calcAve(self, dev, onPeriod, offPeriod):
		accumTimeOn = .9*dev.states["accumTimeOn"] + onPeriod.seconds
		accumTimeOff = .9*dev.states["accumTimeOff"] + offPeriod.seconds
		dev.updateStateOnServer("accumTimeOn", accumTimeOn)
		dev.updateStateOnServer("accumTimeOff", accumTimeOff)
		aveTime = 100*accumTimeOn/(accumTimeOn + accumTimeOff)
		dev.updateStateOnServer("tempControlAveTimeOn", aveTime, decimalPlaces = 1)
		self.logger.info("onperiod in seconds = %s, offperiod in seconds = %s and aveOnTime = %s" % (onPeriod.seconds, offPeriod.seconds, aveTime))

	
	
	
	
	
	
	

	########################################
	def startup(self):
		self.debugLog(u"startup called")

	def shutdown(self):
		self.debugLog(u"shutdown called")

	########################################
	def runConcurrentThread(self):
		try:
			cycles = 0	#cycles counts hardware refresh cycles.  When it hits thermostatPeriod, the group thermostat control loop is executed ensuring that all hardware states have been updated between thermostat cycles
			while True:
				cycles += 1
				for dev in indigo.devices.iter("self"):
					if not dev.deviceTypeId == "mitsubishiHVACGroup":
						if not dev.enabled or not dev.configured:
								continue

					# Plugins that need to poll out the status from the thermostat
					# could do so here, then broadcast back the new values to the
					# Indigo Server.
						self.checkOffTimerExpiration(dev)
						self._refreshStatesFromHardware(dev, False, False)
					
					else:
						if not dev.enabled or not dev.configured:
								continue
						
					# Plugins that need to poll out the status from the thermostat
					# could do so here, then broadcast back the new values to the
					# Indigo Server.
						self.checkOffTimerExpiration(dev)
						self._refreshStatesFromUnits(dev)
						if cycles%self.thermostatPeriod == 0:
							cycles = 0
							self.groupTemperatureControl(dev)
						

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
		#Initialize the off timer to it's disabled state
		zeroTime = datetime.datetime.min
		zeroString = zeroTime.isoformat()+".000000"
		dev.updateStateOnServer('offTime',zeroString)
		dev.updateStateOnServer('timeRemaining', " ")
		
		
		if dev.deviceTypeId == "mitsubishiHVACGroup":
			# Initialeze the exposed states for the group:  SetpointCool, SetpointHeat, and set Mode to "Off".   All other states will be updated during _refereshStatesFromUnits
			keyValueList = []
			results = self.recoverStatesFromDisk(dev)
			thermStates = ['setpointHeat','setpointCool', 'displayHVACMode', 'hvacOperationMode', 'displaySetpointTemp' ]
			for key in thermStates:
				if results["success"] and key in results["data"]:
					keyValueList.append({'key':key, 'value':results["data"][key]})
				
				else: # State not saved for this device so it is probably just created
					deviceIdList = dev.ownerProps.get("groupMembers")
					for tmpDev in indigo.devices.iter("self.mitsubishiHVACDuctless"):
						if str(tmpDev.id) in deviceIdList:   #Device is in the group
							keyValueList.append({'key':key, 'value':tmpDev.states[key]})# Initialize Group setpoints to the setpoint of one of the units in the group
			now = datetime.datetime.today()		
			nowString = now.isoformat()
			keyValueList.append({'key':"tempControlOffTime", 'value':nowString})
			keyValueList.append({'key':"tempControlOnTime", 'value':nowString})
			dev.updateStatesOnServer(keyValueList)
			self.saveStatesToDisk(dev, keyValueList)
				
			
				
	def deviceStopComm(self, dev):
		# Called when communication with the hardware should be shutdown.
		pass

		
		
	########################################
	# These are wrapper callbacks.  They are called if the device being controlled is a group device
	######################
	def actionControlGroupThermostat(self, action, dev):
		self.logger.info("************Group Control ***********")
		self.logger.info("Action: "+ str(action.__class__.__name__))
		self.logger.info("Someone asked for something - Mitsubishi HVAC GROUP Thermostat Action Callback  \"%s\"%s\" %s" % (dev.name, action.description, ".") )
		deviceIdList = dev.ownerProps.get("groupMembers")
		###### SET HVAC MODE ######		
		if action.thermostatAction == indigo.kThermostatAction.SetHvacMode:
			# First update the ThermostatModes in Indigo for this device
			keyValueList = []
			keyValueList.append({'key':'displayHVACMode', 'value':kHvacModeEnumToStrMap[action.actionMode]})
			keyValueList.append({'key':'hvacOperationMode', 'value': action.actionMode})
			dev.updateStatesOnServer(keyValueList)
			self.saveStatesToDisk(dev, keyValueList)
			
			#Then, if there is no Automated Temp Control for this Group update each device that is in the group
			# if there is automated temp control, then turn each unit in the group off so the automated thermostat can control them
			for tmpDev in indigo.devices.iter("self.mitsubishiHVACDuctless"):
				if str(tmpDev.id) in deviceIdList:   #Device is in the group
					if dev.ownerProps.get("groupAutomatedTempControl"):
						action.actionMode = indigo.kHvacMode.Off
					self.actionControlThermostat( action, tmpDev)
					
							
									
								
								

		###### SET FAN MODE ######
		elif action.thermostatAction == indigo.kThermostatAction.SetFanMode:
			keyValueList = []
			keyValueList.append({'key':'displayFanSpeed', 'value':action.actionValue})
			dev.updateStatesOnServer(keyValueList)
			self.saveStatesToDisk(dev, keyValueList)

			#Then update each device that is in the group
			for tmpDev in indigo.devices.iter("self.mitsubishiHVACDuctless"):
				if str(tmpDev.id) in deviceIdList:   #Device is in the group
					self.actionControlThermostat( action, tmpDev)
	
			
		###### SET COOL SETPOINT ######
		elif action.thermostatAction == indigo.kThermostatAction.SetCoolSetpoint:
			newSetpoint = action.actionValue
			keyValueList = []
			for key in ['displaySetpointCool','setpointCool', 'displaySetpointTemp']:
				keyValueList.append({'key':key, 'value':newSetpoint, 'decimalPlaces':0})
			dev.updateStatesOnServer(keyValueList)
			self.saveStatesToDisk(dev, keyValueList)
			
			
			#Then, if there is no Automated Temp Contro for this Group update each device that is in the group
			if dev.ownerProps.get("groupAutomatedTempControl"):
				#for tmpDev in indigo.devices.iter("self.mitsubishiHVACDuctless"):
					#if str(tmpDev.id) in deviceIdList:   #Device is in the group
					#	self.actionControlThermostat( action, tmpDev)
				newSetpoint = newSetpoint-self.groupTempOffset
			for tmpDev in indigo.devices.iter("self.mitsubishiHVACDuctless"):
				if str(tmpDev.id) in deviceIdList:   #Device is in the group
					self._handleChangeSetpointAction(tmpDev, newSetpoint, u"change cool setpoint", u"setpointCool")
					self.logger.info("Adjusting Group(ActionControlGroup) \"%s device: \"%s Current Temp:\"%s  turning the AC down to  \"%s" % (dev.name, tmpDev.name, dev.states["temperatureInput1"], str(newSetpoint)) )
				
			
			
		###### SET HEAT SETPOINT ######
		elif action.thermostatAction == indigo.kThermostatAction.SetHeatSetpoint:
			newSetpoint = action.actionValue
			keyValueList = []
			for key in ['displaySetpointHeat','setpointHeat', 'displaySetpointTemp']:
				keyValueList.append({'key':key, 'value':newSetpoint})
			dev.updateStatesOnServer(keyValueList)
			self.saveStatesToDisk(dev, keyValueList)
			
			#Then, if there is no Automated Temp Control for this Group update each device that is in the group
			if dev.ownerProps.get("groupAutomatedTempControl"):
				newSetpoint = newSetpoint+self.groupTempOffset
			for tmpDev in indigo.devices.iter("self.mitsubishiHVACDuctless"):
				if str(tmpDev.id) in deviceIdList:   #Device is in the group
					self._handleChangeSetpointAction(tmpDev, newSetpoint, u"change heat setpoint", u"setpointHeat")
					self.logger.info("Adjusting Group(ActionControlGroup) \"%s device: \"%s Current Temp:\"%s  turning the heat up to  \"%s" % (dev.name, tmpDev.name, dev.states["temperatureInput1"], str(newSetpoint)) )


				
		###### DECREASE/INCREASE COOL SETPOINT ######
		elif action.thermostatAction == indigo.kThermostatAction.DecreaseCoolSetpoint:
			self.logger.info("*****DECREASE/INCREASE COOL SETPOINT Not supported Function ")
			
		elif action.thermostatAction == indigo.kThermostatAction.IncreaseCoolSetpoint:
			self.logger.info("*****DECREASE/INCREASE COOL SETPOINT Not supported Function ")
			
		###### DECREASE/INCREASE HEAT SETPOINT ######
		elif action.thermostatAction == indigo.kThermostatAction.DecreaseHeatSetpoint:
			self.logger.info("*****DECREASE/INCREASE COOL SETPOINT Not supported Function ")
			
		elif action.thermostatAction == indigo.kThermostatAction.IncreaseHeatSetpoint:
			self.logger.info("*****DECREASE/INCREASE COOL SETPOINT Not supported Function ")
		
		###### REQUEST STATE UPDATES ######
		elif action.thermostatAction in [indigo.kThermostatAction.RequestStatusAll, indigo.kThermostatAction.RequestMode, indigo.kThermostatAction.RequestEquipmentState, indigo.kThermostatAction.RequestTemperatures, indigo.kThermostatAction.RequestHumidities,indigo.kThermostatAction.RequestDeadbands, indigo.kThermostatAction.RequestSetpoints]:
			self._refreshStatesFromHardware(dev, True, False)
			self.logger.info(u"Requested Hardware Status for Mitsubishi unit  \"%s\" %s" % (dev.name, "."))
			
	
	
	
	########################################
	# Thermostat Action callback
	######################
	# Main thermostat action bottleneck called by Indigo Server.
	def actionControlThermostat(self, action, dev):
		if dev.deviceTypeId == "mitsubishiHVACGroup":
			self.actionControlGroupThermostat(action, dev)
		else:
			###### SET HVAC MODE ######
			self.logger.info("Someone asked for something - Mitsubishi HVAC Thermostat Action Callback  \"%s\"%s\" %s" % (dev.name, action.description, ".") )
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
				self.logger.info(u"Requested Hardware Status for Mitsubishi unit  \"%s\" %s \" %s" % (dev.name, str(action),"."))
				
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

		