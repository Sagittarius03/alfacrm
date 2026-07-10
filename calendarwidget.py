import kivy
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.image import Image
from kivy.uix.behaviors import ButtonBehavior
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import get_color_from_hex
from kivy.core.text import LabelBase
from kivy.metrics import dp
from datetime import datetime, timedelta
import threading
import os
import base64
from io import BytesIO

from alfacrm_api import AlfaCRMApi
from database import Database
from notification_manager import NotificationManager
from scheduler import Scheduler
from config_manager import ConfigManager
from logo_base64 import LOGO_BASE64


