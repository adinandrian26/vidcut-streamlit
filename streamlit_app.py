import streamlit as st

st.set_page_config(page_title="VidCut Web", layout="wide")

st.session_state.setdefault("job", "proyek_baru")

page = st.navigation(
    [
        st.Page("app_pages/01_naskah.py", title="Naskah & model", icon=":material/description:"),
        st.Page("app_pages/02_vo.py", title="Voice over & Clone", icon=":material/mic:"),
        st.Page("app_pages/03_gambar.py", title="Gambar", icon=":material/image:"),
        st.Page("app_pages/04_timeline.py", title="Timeline CapCut", icon=":material/movie:"),
    ]
)
page.run()
