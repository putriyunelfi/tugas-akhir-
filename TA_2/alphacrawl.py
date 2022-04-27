#!/usr/bin/python

import argparse
from traceback import print_tb
# TorCrawl Modules
from modules.crawler import *
from modules.checker import *

help = '''
Umum:
-h, --help         : Bantuan

Crawler:
-p, --cpause      : Untuk mengatur lama waktu pause saat crawling (Default: 0)
'''




def main():
	# inisialisasi nilai default  variabel
	cpause = 0

	parser = argparse.ArgumentParser(
		description="AlphaCrawl.py adalah crawler berbahasa python yang dapat digunakan untuk melakukan crawling pada Darkweb.")
	
	parser.add_argument(
        '-p',
        '--cpause',
        help='Untuk mengatur lama waktu pause saat crawling (Default: 0)'
    )

	args = parser.parse_args()

	# mengubah argumen parser menjadi variabel

	if args.cpause:
		cpause = args.cpause

	# Cek Layanan TOR
	checktor()

	# pemanggilan proses crawling
	crawl()
	print("\n\n** Proses Crawling Selesai **\n")

if __name__ == "__main__":
    main()
