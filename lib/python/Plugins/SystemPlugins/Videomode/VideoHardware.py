from Screens.Screen import Screen
from Plugins.Plugin import PluginDescriptor

from enigma import eTimer

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Pixmap import Pixmap
from Screens.MessageBox import MessageBox
from Screens.Setup import SetupSummary
from Components.ConfigList import ConfigListScreen
from Components.config import getConfigListEntry, config, ConfigSelection, ConfigSubDict, ConfigYesNo

from Tools.CList import CList

# The "VideoHardware" is the interface to /proc/stb/video.
# It generates hotplug events, and gives you the list of 
# available and preferred modes, as well as handling the currently
# selected mode. No other strict checking is done.
class VideoHardware:
	rates = { } # high-level, use selectable modes.

	modes = { }  # a list of (high-level) modes for a certain port.

	rates["PAL"] =			{ "50Hz":		{ 50: "pal", 60: "pal"},
												"60Hz":		{ 50: "pal60", 60: "pal60"},
												"multi":	{ 50: "pal", 60: "pal60"} }
	rates["NTSC"] =			{ "60Hz": 	{ 50: "ntsc", 60: "ntsc"} }
	rates["Multi"] =		{ "multi": 	{ 50: "pal", 60: "ntsc"} }
	rates["720p"] =			{	"50Hz": 	{ 50: "720p50", 60: "720p50"},
												"60Hz": 	{ 50: "720p", 60: "720p"},
												"multi": 	{ 50: "720p50", 60: "720p"} }
	rates["1080i"] =		{ "50Hz":		{ 50: "1080i50", 60: "1080i50"},
												"60Hz":		{ 50: "1080i", 60: "1080i"},
												"multi":	{ 50: "1080i50", 60: "1080i"} }
	rates["PC"] = { 
		"1024x768": { 60: "1024x768"}, # not possible on DM7025
		"800x600" : { 60: "800x600"},  # also not possible
		"720x480" : { 60: "720x480"},
		"720x576" : { 60: "720x576"},
		"1280x720": { 60: "1280x720"},
		"1280x720 multi": { 50: "1280x720_50", 60: "1280x720"},
		"1920x1080": { 60: "1920x1080"},
		"1920x1080 multi": { 50: "1920x1080", 60: "1920x1080_50"},
		"1280x1024" : { 60: "1280x1024"},
		"1366x768" : { 60: "1366x768"},
		"1366x768 multi" : { 50: "1366x768", 60: "1366x768_50"},
		"1280x768": { 60: "1280x768"},
		"640x480" : { 60: "640x480"} 
	}

	modes["Scart"] = ["PAL", "NTSC", "Multi"]
	modes["YPbPr"] = ["720p", "1080i"]
	modes["DVI"] = ["720p", "1080i", "PC"]

	widescreen_modes = set(["720p", "1080i"])

	def __init__(self):
		self.last_modes_preferred =  [ ]
		self.on_hotplug = CList()

		self.readAvailableModes()

		self.createConfig()
#		self.on_hotplug.append(self.createConfig)

		self.readPreferredModes()

		config.av.aspect.addNotifier(self.updateAspect)
		config.av.policy_169.addNotifier(self.updateAspect)
		config.av.policy_43.addNotifier(self.updateAspect)

		# until we have the hotplug poll socket
#		self.timer = eTimer()
#		self.timer.callback.append(self.readPreferredModes)
#		self.timer.start(1000)

	def readAvailableModes(self):
		try:
			modes = open("/proc/stb/video/videomode_choices").read()[:-1]
		except IOError:
			print "couldn't read available videomodes."
			self.modes_available = [ ]
			return
		self.modes_available = modes.split(' ')

	def readPreferredModes(self):
		try:
			modes = open("/proc/stb/video/videomode_preferred").read()[:-1]
			self.modes_preferred = modes.split(' ')
		except IOError:
			print "reading preferred modes failed, using all modes"
			self.modes_preferred = self.modes_available

		if self.modes_preferred != self.last_modes_preferred:
			self.last_modes_preferred = self.modes_preferred
			print "hotplug on dvi"
			self.on_hotplug("DVI") # must be DVI

	# check if a high-level mode with a given rate is available.
	def isModeAvailable(self, port, mode, rate):
		rate = self.rates[mode][rate]
		for mode in rate.values():
			# DVI modes must be in "modes_preferred"
#			if port == "DVI":
#				if mode not in self.modes_preferred and not config.av.edid_override.value:
#					print "no, not preferred"
#					return False
			if mode not in self.modes_available:
				return False
		return True

	def isWidescreenMode(self, port, mode):
		return mode in self.widescreen_modes

	def setMode(self, port, mode, rate, force = None):
		print "setMode - port:", port, "mode:", mode, "rate:", rate
		# we can ignore "port"
		self.current_mode = mode
		modes = self.rates[mode][rate]

		mode_50 = modes.get(50)
		mode_60 = modes.get(60)
		if mode_50 is None or force == 60:
			mode_50 = mode_60
		if mode_60 is None or force == 50: 
			mode_60 = mode_50

		try:
			open("/proc/stb/video/videomode_60hz", "w").write(mode_50)
			open("/proc/stb/video/videomode_50hz", "w").write(mode_60)
		except IOError:
			try:
				# fallback if no possibility to setup 50/60 hz mode
				open("/proc/stb/video/videomode", "w").write(mode_50)
			except IOError:
				print "setting videomode failed."

		try:
			open("/etc/videomode", "w").write(mode_50) # use 50Hz mode (if available) for booting
		except IOError:
			print "writing initial videomode to /etc/videomode failed."

		self.updateAspect(None)

	def saveMode(self, port, mode, rate):
		config.av.videoport.value = port
		config.av.videomode[port].value = mode
		config.av.videorate[mode].value = rate

	def isPortAvailable(self, port):
		# fixme
		return True

	def isPortUsed(self, port):
		if port == "DVI":
			self.readPreferredModes()
			return len(self.modes_preferred) != 0
		else:
			return True

	def getPortList(self):
		return [port for port in self.modes if self.isPortAvailable(port)]

	# get a list with all modes, with all rates, for a given port.
	def getModeList(self, port):
		print "getModeList for port", port
		res = [ ]
		for mode in self.modes[port]:
			# list all rates which are completely valid
			rates = [rate for rate in self.rates[mode] if self.isModeAvailable(port, mode, rate)]

			# if at least one rate is ok, add this mode
			if len(rates):
				res.append( (mode, rates) )
		return res

	def createConfig(self, *args):
		# create list of output ports
		portlist = self.getPortList()

		# create list of available modes
		config.av.videoport = ConfigSelection(choices = [(port, _(port)) for port in portlist])
		config.av.videomode = ConfigSubDict()
		config.av.videorate = ConfigSubDict()

		for port in portlist:
			modes = self.getModeList(port)
			if len(modes):
				config.av.videomode[port] = ConfigSelection(choices = [mode for (mode, rates) in modes])
			for (mode, rates) in modes:
				config.av.videorate[mode] = ConfigSelection(choices = rates)

	def setConfiguredMode(self):
		port = config.av.videoport.value
		if port not in config.av.videomode:
			print "current port not available, not setting videomode"
			return

		mode = config.av.videomode[port].value

		if mode not in config.av.videorate:
			print "current mode not available, not setting videomode"
			return

		rate = config.av.videorate[mode].value
		self.setMode(port, mode, rate)
		

	def updateAspect(self, cfgelement):
		# determine aspect = {any,4:3,16:9,16:10}
		# determine policy = {bestfit,letterbox,panscan,nonlinear}

		# based on;
		#   config.av.videoport.value: current video output device
		#     Scart: 
		#   config.av.aspect:
		#     4_3:            use policy_169
		#     16_9,16_10:     use policy_43
		#     auto            always "bestfit"
		#   config.av.policy_169
		#     letterbox       use letterbox
		#     panscan         use panscan
		#     scale           use bestfit
		#   config.av.policy_43
		#     pillarbox       use panscan
		#     panscan         use letterbox  ("panscan" is just a bad term, it's inverse-panscan)
		#     nonlinear       use nonlinear
		#     scale           use bestfit

		port = config.av.videoport.value
		if port not in config.av.videomode:
			print "current port not available, not setting videomode"
			return
		mode = config.av.videomode[port].value

		force_widescreen = self.isWidescreenMode(port, mode)

		is_widescreen = force_widescreen or config.av.aspect.value in ["16_9", "16_10"]
		is_auto = config.av.aspect.value == "auto"

		if is_widescreen:
			if force_widescreen:
				aspect = "16:9"
			else:
				aspect = {"16_9": "16:9", "16_10": "16:10"}[config.av.aspect.value]
			policy = {"pillarbox": "panscan", "panscan": "letterbox", "nonlinear": "nonlinear", "scale": "bestfit"}[config.av.policy_43.value]
		elif is_auto:
			aspect = "any"
			policy = "bestfit"
		else:
			aspect = "4:3"
			policy = {"letterbox": "letterbox", "panscan": "panscan", "scale": "bestfit"}[config.av.policy_169.value]

		print "-> setting aspect, policy", aspect, policy
		open("/proc/stb/video/aspect", "w").write(aspect)
		open("/proc/stb/video/policy", "w").write(policy)

config.av.edid_override = ConfigYesNo(default = False)
video_hw = VideoHardware()
video_hw.setConfiguredMode()