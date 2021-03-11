#!/usr/bin/env python3


import re
import os
import pprint



with open("report.txt", "r") as fp:
    content = fp.readlines()
    # *** CID 206023:  Integer handling issues  (BAD_SHIFT)

    #results = re.match(r'^\*\*\* CID ([0-9]+):\s+(.*).*', content,
    #re.MULTILINE)
    entries = {}
    cid = {}
    lines = []
    for line in content:
        entry = re.search(r'^\*\* CID ([0-9]+):\s+(.*)$', line, re.MULTILINE)
        if entry:
            if lines:
                cid['lines'] = lines
                lines = []
            if cid:
                entries[cid.get('cid')] = cid
            cid = {
                'cid': entry.group(1),
                'violation': entry.group(2)
                }

        if cid.get('cid'):
            code = re.match(r'(\/.*?\.[\w:]+): (\d+) in (\w+)', line)
            if code:
                cid['file'] = code.group(1)
                cid['line'] = code.group(2)
                cid['function'] = code.group(3)

            source = re.match(r'([\d+|>+].*)', line)
            if source:
                lines.append(source.group(1))





    pprint.pprint(entries)

