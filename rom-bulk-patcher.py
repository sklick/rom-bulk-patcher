#!/usr/bin/python3

"""rom-bulk-patcher.py: Bulk patch rom sets using a publically available database of translations."""

__author__      = "sklick"
__copyright__   = "Copyright 2021, sklick"
__version__     = "0.0.2"
__credits__     = ["sklick", "mibro"]
__license__     = "MIT"
__status__      = "Prealpha"

import os, sys, re, io, glob, zlib, urllib.parse, urllib.request, zipfile
import xml.etree.ElementTree as ET, bps.apply, ips_util, fuzzywuzzy.fuzz

def run_patches(set_name:str, rom_dir:str, out_dir:str=None, check_finalcrc:bool=True, search:str=None, download_only:bool=False, stop_on_error:bool=False, crc_search_limit:int=10):
    if out_dir == None:
        print('using rom_dir as out_dir')
        out_dir = rom_dir
    
    xml_name  = os.path.join('database', '{}.xml'.format(set_name))
    patch_dir = os.path.join(os.path.abspath(os.path.split(__file__)[0]), 'patches', set_name)

    # If a database file is missing, download the databases from the publically available RHDB project.
    if not os.path.isfile(xml_name):
        rhdb_file = 'RHDB_App_v0.7.2.zip'
        if not os.path.isfile(rhdb_file):
            # If the RHDB file is not present, try to download it.
            with urllib.request.urlopen('https://romhackdb.com/releases/' + rhdb_file) as dl_file:
                z = zipfile.ZipFile(io.BytesIO(dl_file.read()))
                for file in z.namelist():
                    if file.startswith('database'):
                        z.extract(file)    
        else:
            # Extract RHDB if it is was locally found.
            z = zipfile.ZipFile(rhdb_file)
            for file in z.namelist():
                if file.startswith('database'):
                    z.extract(file)    

    # Check for/make required directories.
    if not os.path.isfile(xml_name):
        print('xml database "{}" not found'.format(xml_name), file=sys.stderr)
        exit(1)
    if not os.path.isdir(rom_dir):
        print('set directory "{}" not found'.format(rom_dir), file=sys.stderr)
        exit(1)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    if not os.path.isdir(patch_dir):
        os.makedirs(patch_dir)

    # Parse database xml-file.
    root_el   = ET.parse(xml_name).getroot()
    header_el = root_el[0]
    games_el  = root_el[1:]

    # Print the header of the patch database.
    print('[=== ROM Set ===]')
    for el in list(header_el):
        print(' {:20} : {} '.format(el.tag, el.text))

    # Prepare the file extension for the rom set. Defaults to ".bin" if all other detection methods fail.
    ext_map = {
        'Gameboy'       : 'gb',
        'Gameboy Color' : 'gbc',
        'NES'           : 'nes',
        'SNES'          : 'sfc',
        'Genesis'       : 'smd',
    }
    rom_ext = header_el.find('fileextension').text if header_el.find('fileextension') != None else ext_map[set_name] if set_name in ext_map else 'bin'

    games = []
    if search != None:
        # Search fuzzyly for a specific patch by name.
        games = sorted([[el.get('name'), fuzzywuzzy.fuzz.ratio(el.get('name')[:len(search)].upper(), search.upper()), el] for el in games_el], key=lambda x: x[1], reverse=True)
        if games[0][1] <= 50:
            print()
            print('please be more specific with --search. here are some suggestions:')
            for game in games[:min(5, len(games))]:
                print(' - {}'.format(game[0]))
            return
        else:
            games = list(filter(lambda x: x[1] > games[0][1] - ((games[0][1] / 10)), games))
    else:
        games = sorted([[el.get('name'), 100, el] for el in games_el], key=lambda x: x[0])

    # Force crc_search_limit for larger game lists.
    if len(games) > 100 and crc_search_limit == None:
        crc_search_limit = 10

    err_list = []
    
    # Iterate over each game patch entry in the database.
    for name, ratio, game_el in games:

        # Print some general info for the patch.
        print('[--- {} ---]'.format(name))
        if search != None:
            print(' {:20} : {}'.format('search_confidence', '{}%'.format(ratio)))
        patch_version = game_el.find('version').text
        print(' {:20} : {}'.format('patch_version', patch_version))
        patch_author = game_el.find('shortauthor').text
        print(' {:20} : {}'.format('patch_author', patch_author))
        patch_genre = 'T-Eng'
        print(' {:20} : {}'.format('patch_genre', patch_genre))
        patch_type = game_el.find('patchtype').text
        print(' {:20} : {}'.format('patch_type', patch_type))
        patch_file = os.path.abspath(os.path.join(patch_dir, '{}.{}'.format(name, patch_type)))
        print(' {:20} : {} '.format('patch_file', patch_file))
        
        # If patch is not available locally, download it.
        if not os.path.isfile(patch_file):
            patch_url = 'https://romhackdb.com/patches/{}/{}.{}'.format(os.path.splitext(set_name)[0], urllib.parse.quote(name), patch_type)
            print(' {:20} : {} '.format('patch_url', patch_url))
            try:
                urllib.request.urlretrieve(patch_url, patch_file)
            except Exception as ex:
                res = 'could not download patch [{}]'.format(ex)
        # Check patchCRC on local patch file.
        crc = 0
        with open(patch_file, 'rb') as file:
            while chunk := file.read(512):
                crc = zlib.crc32(chunk, crc)
        if not game_el.find('patchCRC').text == '{:08X}'.format(crc):
            res = 'patch_file failed CRC check {} != {}'.format(game_el.find('patchCRC').text, '{:08X}'.format(crc))
        else:
            if download_only:
                # Stop right here, if we are in --downloadonly mode.
                    res = 'patch downloaded successfully'
            else:
                # Cleanup file name in case there is more than one patch per game.
                re_res = re.match('^(.*)_\\d+', name)
                rom_name = name if not re_res else re_res.groups()[0]
                rom_file = os.path.join(rom_dir, '{}.{}'.format(rom_name, rom_ext))
                
                # Fuzzy CRC search: sort all available files by name fuzzily, then search for baseCRC.
                # Can be limited to a certain number of most likely files to increase speed.
                # Only runs if the rom was not found by the name provided in the database.
                if not os.path.isfile(rom_file):
                    files = [[file, fuzzywuzzy.fuzz.ratio(os.path.basename(file), rom_name)] for file in glob.glob(os.path.join(rom_dir, '**'))]
                    files = sorted(files, key=lambda x: x[1], reverse=True)[:len(files) if crc_search_limit == None else crc_search_limit]
                    print(' {:20} : {} '.format('fuzzy_crc', 'checking {} file crc(s)'.format(len(files))))
                    for check_file, ratio in files:
                        crc = 0
                        with open(check_file, 'rb') as file:
                            while chunk := file.read(512):
                                crc = zlib.crc32(chunk, crc)
                        if game_el.find('baseCRC').text == '{:08X}'.format(crc):
                            rom_file = check_file    
                            break
                # Last chance to locate the rom file after a possible fuzzy CRC search.
                if not os.path.isfile(rom_file):
                    res = 'rom not found'
                else:
                    # Check baseCRC on local rom file.
                    crc = 0
                    with open(rom_file, 'rb') as file:
                        while chunk := file.read(512):
                            crc = zlib.crc32(chunk, crc)
                    if not game_el.find('baseCRC').text == '{:08X}'.format(crc):
                        res = 'rom_file failed CRC check {} != {}'.format(game_el.find('baseCRC').text, '{:08X}'.format(crc))           
                    else:
                        out_file = os.path.abspath(os.path.join(out_dir, '{} ({} {} by {}).{}'.format(rom_name, patch_genre, patch_version, patch_author, rom_ext)))
                        print(' {:20} : {} '.format('out_file', out_file))
                        if patch_type not in ['bps', 'ips']:
                            res = 'unsupported patch type "{}"'.format(patch_type)
                        else:
                            if patch_type == 'bps':
                                # Perform a bps patch.
                                try:
                                    source = open(rom_file, 'rb')
                                    target = open(out_file, 'wb')
                                    patch  = open(patch_file, 'rb')
                                    bps.apply.apply_to_files(patch, source, target)
                                except Exception as ex:
                                    res = 'bps patch failed [{}]'.format(ex)
                                if not check_finalcrc:
                                    res = 'patched successfully'
                                else:
                                    # Check finalCRC on patched rom file.
                                    crc = 0
                                    with open(out_file, 'rb') as file:
                                        while chunk := file.read(512):
                                            crc = zlib.crc32(chunk, crc)
                                    if game_el.find('finalCRC').text == '{:08X}'.format(crc):
                                        res = 'patched successfully'
                                    else:
                                        res = 'out_file failed CRC check {} != {}'.format(game_el.find('finalCRC').text, '{:08X}'.format(crc))
                            if patch_type == 'ips':
                                # Perform an ips patch.
                                try:
                                    patch = ips_util.Patch.load(patch_file)
                                    source = open(rom_file, 'rb')
                                    target = open(out_file, 'wb')
                                    target.write(patch.apply(source.read()))
                                    bps.apply.apply_to_files(patch, source, target)
                                except Exception as ex:
                                    res = 'ips patch failed [{}]'.format(ex)                                    
                                if not check_finalcrc:
                                    res = 'patched successfully'
                                else:
                                    # Check finalCRC on patched rom file.
                                    crc = 0
                                    with open(out_file, 'rb') as file:
                                        while chunk := file.read(512):
                                            crc = zlib.crc32(chunk, crc)
                                    if game_el.find('finalCRC').text == '{:08X}'.format(crc):
                                        res = 'patched successfully'
                                    else:
                                        res = 'out_file failed CRC check {} != {}'.format(game_el.find('finalCRC').text, '{:08X}'.format(crc))
                           
        print(' {:20} : {} '.format('result', res))
        # Collect errors for later printing.
        if not res in ['patched successfully', 'patch downloaded successfully']:
            if stop_on_error:
                # if --stoponerror is set, this is where we end processing the file list.
                print('stopped on error', file=sys.stderr)
                break
            err_list.append([name, res])
    
    # Print errors.
    if len(err_list) > 0:
        print('[=== Errors ===]')
        for err in err_list:
            print(' {}:'.format(err[0]))
            print('  {}'.format(err[1]))


import argparse
parser = argparse.ArgumentParser(description='v' + __version__ + '. Apply patch database file against a rom set.')
parser.add_argument('setid',            type=str, help='name of the rom set, i.e. "SNES" (a matching "SNES.xml" database file needs to be located next to this script)')
parser.add_argument('indir',            type=str, help='rom set directory containing the original rom dumps', nargs='?')
parser.add_argument('outdir',           type=str, help='target directory for patched rom files (defaults to indir)', nargs='?', default=None)
parser.add_argument('--search',         type=str, help='filter the patch list to apply only patches that match the PATTERN (uses fuzzy search)', metavar='PATTERN', default=None)
parser.add_argument('--stoponerror',              help='stop processing patch database if a patch fails to apply', action='store_true')
parser.add_argument('--crcsearchlimit', type=int, help='limit the number of maximum file candiates whose CRC should be checked to id a rom that has an unexpected name (0=do not search by CRC)', metavar='N', default=10)
parser.add_argument('--downloadonly',             help='download database and patches, but do not apply patches', action='store_true')
args = parser.parse_args()

if not args.downloadonly and not args.indir:
    parser.error('indir is required if --downloadonly is not specified')

run_patches(args.setid, args.indir, args.outdir, search=args.search, download_only=args.downloadonly, stop_on_error=args.stoponerror, crc_search_limit=args.crcsearchlimit)