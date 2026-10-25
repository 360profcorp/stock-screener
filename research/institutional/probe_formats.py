"""Format probe: file names and header rows of the SEC data sets (no research data kept)."""
import io
import re
import zipfile

import requests

UA = {"User-Agent": "VISAR research 360pro.corp@gmail.com"}


def links(page):
    t = requests.get(page, headers=UA, timeout=60).text
    return sorted(set(re.findall(r'href="([^"]+\.zip)"', t)))


for page in ("https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets",
             "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets",
             "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data"):
    L = links(page)
    print("PAGE", page, len(L))
    for x in L[:6] + ["..."] + L[-6:]:
        print("  ", x)
for url in ("https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/2016q1_form345.zip",
            "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/2016q1_form13f.zip"):
    z = zipfile.ZipFile(io.BytesIO(requests.get(url, headers=UA, timeout=120).content))
    print("ZIP", url)
    for n in z.namelist():
        with z.open(n) as f:
            head = [f.readline().decode("utf-8", "replace").rstrip() for _ in range(3)]
        print("  ", n, z.getinfo(n).file_size)
        for h in head:
            print("     |", h[:300])
L = links("https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data")
if L:
    u = L[-1] if L[-1].startswith("http") else "https://www.sec.gov" + L[-1]
    z = zipfile.ZipFile(io.BytesIO(requests.get(u, headers=UA, timeout=60).content))
    n = z.namelist()[0]
    with z.open(n) as f:
        print("FTD", u, n, [f.readline().decode("latin-1").rstrip() for _ in range(3)])
# rerun
