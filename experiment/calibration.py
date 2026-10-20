import os
import glob
from psychopy import visual, sound
import sys

# import psychopy tobii infant
directory = os.path.dirname(os.path.abspath(__file__))  # folder this script lives in
os.chdir(directory) 
sys.path.append(directory)
from psychopy_tobii_infant import TobiiInfantController

# settings & stimuli
winsize = [1920, 1080]
win = visual.Window(winsize, fullscr=True, allowGUI=False, screen=3, color ="#a6a6a6",units="pix")

CALISTIMS = glob.glob(os.path.join("CalibrationStim", "*.png"))
VideoGrabber = visual.MovieStim(win, os.path.join("CalibrationStim", "Attentiongrabber.mp4"), loop=True, size=[800,450],volume =0.4)  
Sound = sound.Sound(os.path.join(directory, "CalibrationStim", "upchime1.wav"))

# connect to the eye tracker
EyeTracker = TobiiInfantController(win)

# set video playing
VideoGrabber.setAutoDraw(True)
VideoGrabber.play()

# show the relative position of the subject to the eyetracker
EyeTracker.show_status()

# stop the attention grabber
VideoGrabber.setAutoDraw(False)
VideoGrabber.stop()

# run calibration
CALINORMP = [(-0.4, 0.4), (-0.4, -0.4), (0.0, 0.0), (0.4, 0.4), (0.4, -0.4)]
CALIPOINTS = [(x * winsize[0], y * winsize[1]) for x, y in CALINORMP]
success = EyeTracker.run_calibration(CALIPOINTS, CALISTIMS, audio = Sound)
win.flip() 

