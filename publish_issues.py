#!/usr/bin/env python3
#
# Copyright (c) 2017 Intel Corporation
#
# Coverity Automation code is designed to automate the coverity github issue
# creation when there is new issues seen in the coverity webpage based on the
# scan results for the Zephyr project, by eliminating the previously
# existing issues and to create GitHub issues for the new once.

import re
import csv
import os
import sys
import argparse
import requests
import codeowners
from pathlib import Path
import subprocess
import typing
import json

# Fetching the environmental variables set for GitHub Personal Access Token
TOKEN = os.environ.get("GH_TOKEN")
args = None

DEBUG = True


BODY_TEMPLATE = """
Static code scan issues found in file:

https://github.com/zephyrproject-rtos/zephyr/tree/{commit}/{filename}

Category: {category}
Function: `{function}`
Component: {component}
CID: [{cid}](https://scan9.coverity.com/reports.htm#v29726/p12996/mergedDefectId={cid})


Details:

{link}

Please fix or provide comments in coverity using the link:

https://scan9.coverity.com/reports.htm#v29271/p12996.

Note: This issue was created automatically. Priority was set based on classification
of the file affected and the impact field in coverity. Assignees were set using the CODEOWNERS file.
"""

BODY_TEMPLATE_DETAILED = """
Static code scan issues found in file:

https://github.com/zephyrproject-rtos/zephyr/tree/{commit}/{filename}#L{line}

Category: {category}
Function: `{function}`
Component: {component}
CID: [{cid}](https://scan9.coverity.com/reports.htm#v29726/p12996/mergedDefectId={cid})


Details:

{link}

```
{code}
```

Please fix or provide comments in coverity using the link:

https://scan9.coverity.com/reports.htm#v29271/p12996

Note: This issue was created automatically. Priority was set based on classification
of the file affected and the impact field in coverity. Assignees were set using the CODEOWNERS file.
"""

# Possible locations of CODEOWNERS file, relative to repository root.
_CODEOWNERS_REL_LOCATIONS = [Path('docs/CODEOWNERS'), Path('.github/CODEOWNERS'), Path('CODEOWNERS')]


def git_repository_root(base_dir: Path, search_parent_directories=True) -> Path:
    dir = base_dir
    while True:
        if (dir / '.git').exists():
            return dir

        if not search_parent_directories:
            break

        if dir == Path('/') or dir == Path():
            break

        dir = dir.parent

    raise FileNotFoundError("Could not find .git directory in:  {base_dir}{msg}".format(
        base_dir=base_dir, msg=' (or any parent)' if search_parent_directories else ''))


def codeowners_path(base_dir: Path) -> Path:
    repo_root = git_repository_root(base_dir=base_dir)
    candidate_paths = [repo_root / location for location in _CODEOWNERS_REL_LOCATIONS]
    path = next((p for p in candidate_paths if p.exists()), None)
    if path is None:
        raise FileNotFoundError("Could not find CODEOWNERS file in any of the following locations: ".format(
            '; '.join(map(str, candidate_paths))))
    return path


def list_files(paths: typing.Iterable[Path], untracked: bool = False, recursive: bool = True):
    """ Return an iterable of Paths representing non-ignored files recognized by git. """
    if not recursive:
        raise NotImplementedError('Only recursive traversal supported right now; got recursive: {!r}'.format(recursive))

    tracked_options = ['--cached', '--others'] if untracked else ['--cached']

    # In the future, we should process the output in a streaming fashion.
    ls_result = subprocess.run(['git', 'ls-files', *tracked_options, *map(str, paths)],
                               check=True, stdout=subprocess.PIPE, universal_newlines=True)
    return [Path(p) for p in ls_result.stdout.splitlines()]


class Issues:

    def __init__(self):
        self.repo = args.repo
        self.org = args.org
        self.issues_url = "https://github.com/%s/%s/issues" %(self.org, self.repo)
        self.github_url = 'https://api.github.com/repos/%s/%s' % (self.org, self.repo)

        self.api_token = TOKEN
        self.headers = {}
        self.headers['Authorization'] = 'token %s' % self.api_token
        self.headers['Accept'] = 'application/vnd.github.golden-comet-preview+json'
        self.issues = []

    def list_issues(self, url):
        response = requests.get("%s" %(url), headers=self.headers)

        if response.status_code != 200:
            raise RuntimeError(
                "Failed to get issue due to unexpected HTTP status code: {}".format(response.status_code)
                )
        self.issues = self.issues + response.json()
        try:
            print("Getting more issues...")
            next_issues = response.links["next"]
            if next_issues:
                next_url = next_issues['url']
                #print(next_url)
                self.list_issues(next_url)
        except KeyError:
            print("no more pages")

    def get_all(self):
        self.list_issues("%s/issues?state=all&labels=Coverity,bug" %self.github_url)


    def post(self, content):
        response = requests.post("%s/issues" %(self.github_url), headers=self.headers, data=json.dumps(content))

        print(json.dumps(content))
        if response.status_code != 201:
            raise RuntimeError(
                "Failed to post issue due to unexpected HTTP status code: {}: {}".format(
                    response.status_code, response.reason)
                )


def find_codeowner(filename):

    codeowners_path = args.codeowners_file
    with open(codeowners_path, 'r') as codeowners_file:
        rules = codeowners.parse_codeowners(codeowners_file, source_filename=codeowners_path)

    paths = list_files((filename,), untracked=True, recursive=True)
    repo_root = args.git_root

    for p in paths:
        match_result = codeowners.match(rules, p.resolve().relative_to(repo_root), is_dir=True)
        return match_result



def parse_email(email_content):
    entries = {}
    with open(email_content, "r") as fp:
        content = fp.readlines()

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
                code = re.match(r'(\/.*?\.[\w:]+): (\d+) in (\w*)\(\)', line)
                if code:
                    cid['file'] = code.group(1)
                    cid['line'] = code.group(2)
                    cid['function'] = code.group(3)

                source = re.match(r'([\d+|>+].*)', line)
                if source:
                    lines.append(source.group(1))

        if cid:
            cid['lines'] = lines
            entries[cid.get('cid')] = cid

    return entries

def main():
    global args
    parser = argparse.ArgumentParser(description="Upload coverity issues to Github")


    parser.add_argument("-y", "--dryrun",
                        action="store_true",
                        help="Dry run, do not post anything.")
    parser.add_argument("-O", "--outstanding",
                        required=True,
                        help="CSV file exported from coverity for outstanding issues")
    parser.add_argument("-o", "--org",
                        default="zephyrproject-rtos",
                        help="Github organisation")
    parser.add_argument("-r", "--repo",
                        default="zephyr",
                        help="Github repo",
                        )
    parser.add_argument("-w", "--codeowners-file",
                        required=False, help="Path to CODEOWNERS file")
    parser.add_argument("-R", "--git-root",
                        required=False, help="Git repo root")
    parser.add_argument("-e", "--email-content",
                        required=False,
                        help="Contents of email from coverity with all new violations")
    parser.add_argument("-C", "--commit-hash",
                        required=False,
                        default="master",
                        help="Hash of the commit that was scanned")

    args = parser.parse_args()

    if not TOKEN:
        sys.exit("token missing")


    if args.outstanding and not os.path.exists(args.outstanding):
        sys.exit("File {} does not exist.".format(args.outstanding))

    coverity_issues = Issues()
    coverity_issues.get_all()

    if DEBUG:
        for issue in coverity_issues.issues:
            print("{} - {}".format(issue['number'], issue['title']))

    print("found {} existing issues.".format(len(coverity_issues.issues)))

    cids = set()
    cr = None

    for issue in coverity_issues.issues:
        cid = re.compile("CID[ ]?:[ ]?(?P<cid>[0-9]+)")
        match = cid.search(issue['title'])
        if not match:
            continue
        cid = int(match.groupdict()['cid'])
        cids.add(cid)

    email_contents = {}

    if args.email_content:
        email_contents = parse_email(args.email_content)

    count = 0
    with open(args.outstanding) as csv_file:
        cr = csv.DictReader(csv_file)
        for row in cr:
            #print(row)
            cid = int(row['CID'])
            if row['File'].startswith("/home"):
                continue
            filename = row['File'][1:]
            title = "[Coverity CID: {}] {} in {}".format(row['CID'], row['Type'], filename)
            if cid in cids:
                print("Skipping CID {}, already reported.".format(cid))
                continue
            elif 'twister-out' in filename:
                print("Skipping CID {}, generated code.".format(cid))
                continue
            else:
                line = row['Line Number']
                if line == 'Various':
                    link = f"https://github.com/zephyrproject-rtos/zephyr/blob/{args.commit_hash}/{filename}"
                else:
                    link = f"https://github.com/zephyrproject-rtos/zephyr/blob/{args.commit_hash}/{filename}#L{line}"
                if email_contents and email_contents.get(row['CID']):
                    details = email_contents[row['CID']]
                    line = details.get('line')
                    code = "\n".join(details['lines'])
                    body = BODY_TEMPLATE_DETAILED.format(
                        filename=filename,
                        link=link,
                        line=line or 1,
                        category=row['Category'],
                        function=row['Function'],
                        component=row['Component'],
                        cid=row['CID'],
                        commit=args.commit_hash,
                        code=code
                        )
                else:
                    body = BODY_TEMPLATE.format(
                        filename=filename,
                        category=row['Category'],
                        link=link,
                        function=row['Function'],
                        component=row['Component'],
                        cid=row['CID'],
                        commit=args.commit_hash
                        )

            print("Creating new issue with title: {}".format(title))

            count += 1
            assignees = []
            if args.codeowners_file:
                results = find_codeowner(filename)
                if results:
                    owners = results.owners
                    for o in owners:
                        if not o in ['@otavio', '@franciscomunoz']:
                            assignees.append(o[1:])

            prio = "priority: medium"
            if filename.startswith("tests") or filename.startswith("samples"):
                prio = "priority: low"

            if row['Impact'] in ['Low','Medium']:
                prio = "priority: low"

            new_issue = {
                "title": title,
                "body": body,
                "labels":
                [
                    "bug", "Coverity", prio
                ],
                "assignees": assignees
            }

            if not args.dryrun:
                coverity_issues.post(new_issue)
            else:
                print(title)
                print(body)
                print("Not posting anything")


    print("Created {} issues.".format(count))



if __name__ == "__main__":
    main()
