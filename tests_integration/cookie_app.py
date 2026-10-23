"""Integration probe for the Schwab renewal browser binding (CI only, dummy secrets).
Runs the REAL trade_tab helpers in a real Streamlit server: the cookie is set by
_set_browser_cookie, read by _browser_cookie, and a return is processed by
handle_schwab_return exactly as in the app."""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

import schwab_auth  # noqa: E402
import trade_tab  # noqa: E402

X = trade_tab.TX["en"]
trade_tab.handle_schwab_return(X, trade_tab._secret("STATE_PASSWORD"))
r = st.session_state.get("sch_last_result")
st.text("RESULT=" + ("none" if not r else f"{r.get('step')}|{r.get('state_check')}|{r.get('ok')}"))
c = trade_tab._browser_cookie()
st.text("COOKIE=" + (hashlib.sha256(c.encode()).hexdigest()[:12] if c else "absent"))
if st.button("issue"):
    b = schwab_auth.new_browser_secret()
    st.session_state["b"] = b
    st.session_state["s"] = trade_tab._pending_states().issue(b)
if "b" in st.session_state:
    trade_tab._set_browser_cookie(st.session_state["b"], schwab_auth.STATE_TTL)
    st.text("SET=" + hashlib.sha256(st.session_state["b"].encode()).hexdigest()[:12])
    st.text("STATE=" + st.session_state["s"])
st.text("READY")
