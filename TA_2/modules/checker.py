#!/usr/bin/python

import sys
import re
import subprocess
import os
from urllib.parse import urlparse


# Pengecekan TOR Service 
def checktor():
	checkfortor = subprocess.check_output(['ps', '-e'])

	def findwholeword(w):
		return re.compile(r'\b({0})\b'.format(w), flags=re.IGNORECASE).search

	if findwholeword('tor')(str(checkfortor)):
		print("## Layanan TOR telah berjalan!")
	else:
		print("## Layanan TOR BELUM berjalan!")
		print('## Aktifkan tor menggunakan perintah \'service tor start\'')
		sys.exit(2)

