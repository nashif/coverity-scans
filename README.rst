

- Download Outstanding+Defects.csv from coverity web UI
- Run dos2unix on Outstanding+Defects.csv
- Copy email content from coverity into report.txt
- run script:
        python3 ../coverity/publish_issues.py --outstanding Outstanding+Defects.csv \
        --codeowners-file CODEOWNERS \
        -R /Users/anashif/zephyr/zephyrproject/zephyr \
        -e report.txt \
        -C c9a2a5e7fb0194bfb168f5aa1a0a83c73f62acb3
