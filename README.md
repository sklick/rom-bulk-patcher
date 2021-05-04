# rom-bulk-patcher

Python3 script that applies a multitude of patches to ROM files from different system.

It applies a comprehensive list of translation patches to a rom set, up to a full set such as No-Intro or GoodSet, trying to keep the patched file names consistent with the existing ROMs.

The database of patches was assembled by https://romhackdb.com/, so all credit for the patch database goes to the author of this project. Sadly, the program provided to match the ROM files to the correct patches did not work for me and no source code was provided.

So this script was created to do the job using the same database files.

This script is at the moment heavily dependend on the afformentioned site staying online and accessible. If this turns out to be to cumbersome in the future, the script will develope away from this dependency.

## Usage

Take a look at the **-h** listing:

```
usage: rom-bulk-patcher.py [-h] [--setid [SETID]] [--search PATTERN] [--stoponerror] [--crcsearchlimit N] [--downloadonly] [indir] [outdir]

v0.0.3. Apply patch database file against a rom set.

positional arguments:
  indir               rom set directory containing the original rom dumps
  outdir              target directory for patched rom files (defaults to indir)

optional arguments:
  -h, --help          show this help message and exit
  --setid [SETID]     name of the rom set, i.e. "SNES" (a matching "SNES.xml" database file needs to be located next to this script)
  --search PATTERN    filter the patch list to apply only patches that match the PATTERN (uses fuzzy search)
  --stoponerror       stop processing patch database if a patch fails to apply
  --crcsearchlimit N  limit the number of maximum file candiates whose CRC should be checked to id a rom that has an unexpected name (0=do not search by CRC)
  --downloadonly      download database and patches, but do not apply patches
```

## Hints

- `indir` is only optional when using `--downloadonly`.
- `outdir` defaults to `indir`. If you do not want your original and patched files to mix, use this option.
- `--setid` must be a casesensitive match to one of the database files. The script will attempt to find a matching database based on the `indir` 
- Errors that occure during bulk patching will be listed again at the end of the process, but you can terminated the process on the first error with `--stoponerror` to work on each problematic patch before proceeding.

## Matching process

Each patch comes with a name and checksum value to identify the original file it should be applied to. Before patching the checksum will always be validated or else an error will occure. If no perfect match by name can be found, the script will try to find a file in the `indir` that matches the [CRC](https://en.wikipedia.org/wiki/Cyclic_redundancy_check).

This process can be very time consuming on large sets or large files, since the whole file needs to be read to calcualed the CRC.

That is why the script employs two strategies to limit the time spend on CRC matching the file.

The first is [fuzzy searching](https://en.wikipedia.org/wiki/Approximate_string_matching) for the file name, sorting all available files by how similar they appear to be to the patch name and then searching for the patch's CRC in that order.

Secondly, `--crcsearchlimit` will limit the number of files that are CRC checked before the script gives up and considers the file missing/not found. In case a file is actually missing from the `indir`, this will reduce the time to run the script over the whole set of files significantly.

## Local files

Both the database files and the patches will be kept locally after being downloaded for the first time in the **database** and **patches** directories, next to the script file.


