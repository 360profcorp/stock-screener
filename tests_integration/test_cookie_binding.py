"""Real browser (Chromium via Playwright) + real Streamlit server: the renewal state is bound
to the browser that started it. Run by .github/workflows/schwab-renew-integration.yml."""
import re
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8599"


def text(page, prefix):
    page.wait_for_selector(f"text=/^{prefix}=/", timeout=60000)
    for t in page.locator("pre, code, div").all_inner_texts():
        m = re.search(rf"{prefix}=(\S+)", t)
        if m:
            return m.group(1)
    raise AssertionError(f"{prefix} not found")


def ready(page):
    page.wait_for_selector("text=READY", timeout=90000)


def issue(page):
    page.get_by_role("button", name="issue").click()
    page.wait_for_selector("text=/^STATE=/", timeout=60000)
    page.wait_for_timeout(2000)                                   # let the component run
    return text(page, "STATE"), text(page, "SET")


with sync_playwright() as p:
    br = p.chromium.launch()
    A = br.new_context()
    a = A.new_page()
    a.goto(URL)
    ready(a)
    assert text(a, "COOKIE") == "absent"
    s1, set1 = issue(a)
    names = [c["name"] for c in A.cookies()]
    print("cookies in browser A:", names)
    assert "visar_sch_b" in names, "cookie was not set by the component"
    a.goto(URL)                                                   # new session, same browser
    ready(a)
    assert text(a, "COOKIE") == set1, "Streamlit did not read the cookie back"
    print("1. cookie set by the page and read back by st.context.cookies: OK")

    # 2. a VALID state brought by another browser is rejected before Schwab is called
    B = br.new_context()
    b = B.new_page()
    b.goto(f"{URL}/?code=fake-code&state={s1}")
    ready(b)
    res = text(b, "RESULT")
    print("browser B with A's state:", res)
    assert res.startswith("state|other_browser|False"), res
    assert "code=" not in b.url, b.url
    print("2. valid state from browser A rejected in browser B, URL cleaned: OK")

    # 3. the same browser passes the state check (the fake code then fails at the exchange)
    a.goto(URL)
    ready(a)
    s2, _ = issue(a)
    a.goto(f"{URL}/?code=fake-code&state={s2}")
    ready(a)
    res = text(a, "RESULT")
    print("browser A with its own state:", res)
    assert res.startswith("exchange|None|False"), res
    assert "code=" not in a.url, a.url
    print("3. same browser passes the state check; exchange step reached: OK")

    # 4. replay of the same state is refused
    a.goto(f"{URL}/?code=fake-code&state={s2}")
    ready(a)
    res = text(a, "RESULT")
    assert res.startswith("state|used|False"), res
    print("4. replayed state refused: OK")
    br.close()
print("ALL OK")
