import os
import time

import requests
import streamlit as st

from pipeline import jobs, runner


st.session_state.setdefault("job", "proyek_baru")
st.title("Voice over & Voice Clone")
st.caption("Langkah 2 — pilih jenis suara, lalu buat vo.mp3 dan vo.srt.")

job_path = jobs.job_dir(st.session_state["job"])
naskah_file = job_path / "naskah.txt"
vo_mp3 = job_path / "vo.mp3"
vo_srt = job_path / "vo.srt"
st.info(f"Job: `{st.session_state['job']}`")

if not naskah_file.exists():
    st.warning("Belum ada naskah. Isi dulu di halaman Naskah & model.")
    st.stop()

naskah = naskah_file.read_text(encoding="utf-8-sig").strip()
if not naskah:
    st.warning("Naskah masih kosong.")
    st.stop()

try:
    configured_api = st.secrets.get("VC_API_URL", "")
except Exception:
    configured_api = ""
default_api = configured_api or os.environ.get("VC_API_URL", "http://localhost:8520")
with st.expander("Pengaturan layanan clone"):
    clone_api = st.text_input("URL layanan", value=default_api,
                              key="vo_clone_api")


def api_error(response: requests.Response) -> str:
    try:
        detail = response.json().get("detail", response.text)
    except Exception:
        detail = response.text
    return f"API {response.status_code}: {detail}"


def get_saved_voices() -> tuple[list[dict], str]:
    try:
        response = requests.get(f"{clone_api}/api/voices", timeout=5)
        response.raise_for_status()
        return response.json(), ""
    except requests.RequestException as exc:
        return [], str(exc)


def wait_for_clone(job_id: str, progress, status_box) -> tuple[bool, str]:
    log: list[str] = []
    while True:
        try:
            response = requests.get(f"{clone_api}/api/jobs/{job_id}",
                                    timeout=30)
            if not response.ok:
                return False, api_error(response)
            status = response.json()
        except requests.RequestException as exc:
            return False, f"Tidak bisa membaca progres: {exc}"

        value = max(0, min(100, int(status.get("progress", 0))))
        stage = status.get("status", "")
        detail = status.get("stage_detail", "")
        progress.progress(value, text=f"{value}% — {detail or stage}")
        log.append(f"{value:3d}% [{stage}] {detail}")

        if status.get("warning"):
            status_box.warning(status["warning"])
        if stage == "done":
            return True, "\n".join(log)
        if stage == "failed":
            return False, "\n".join(log) + f"\nERROR: {status.get('error', '')}"
        time.sleep(3)


def download_clone_results(job_id: str) -> None:
    for format_name, destination in (("mp3", vo_mp3), ("srt", vo_srt)):
        response = requests.get(
            f"{clone_api}/api/jobs/{job_id}/audio",
            params={"format": format_name}, timeout=300)
        if not response.ok:
            raise RuntimeError(api_error(response))
        destination.write_bytes(response.content)


saved_voices, clone_api_problem = get_saved_voices()

with st.container(border=True):
    st.subheader("1. Pilih jenis suara")
    voice_mode = st.segmented_control(
        "Jenis suara",
        ["Suara bawaan", "Voice clone"],
        default="Suara bawaan",
        key="vo_mode",
    )

    builtin_choice = None
    rate = "+2%"
    clone_source = None
    selected_voice = None
    upload = None
    youtube_url = ""
    start_seconds = 0.0
    sample_seconds = 30.0
    save_voice = False
    voice_name = ""
    consent = False

    if voice_mode == "Suara bawaan":
        builtin_choice = st.selectbox(
            "Pilih suara",
            ["Ardi (laki-laki)", "Gadis (perempuan)",
             "Rudi Documenter (gaya narasi)"],
            key="vo_builtin_voice",
        )
        rate = st.text_input("Kecepatan", value="+2%", key="vo_rate",
                             help="Contoh: +0%, +2%, atau -5%")
        if builtin_choice == "Rudi Documenter (gaya narasi)":
            st.caption("Preset narasi pitch rendah, energik, dan berjeda dramatis.")
    else:
        if clone_api_problem:
            st.error("Layanan voice clone belum terhubung. Pastikan layanan di "
                     f"`{clone_api}` aktif. Detail: {clone_api_problem}")

        source_options = (["Pakai suara tersimpan", "Buat clone baru"]
                          if saved_voices else ["Buat clone baru"])
        clone_source = st.segmented_control(
            "Sumber clone", source_options, default=source_options[0],
            key="vo_clone_source",
        )

        if clone_source == "Pakai suara tersimpan":
            by_label = {
                f"{voice['nama']} — dibuat {voice.get('dibuat', '-')}": voice
                for voice in saved_voices
            }
            selected_label = st.selectbox("Pilih suara clone",
                                          list(by_label), key="vo_saved_voice")
            selected_voice = by_label[selected_label]
            st.caption("Suara ini langsung dipakai untuk seluruh naskah.")
        else:
            st.markdown("**Buat clone baru dari sampel suara**")
            source_kind = st.segmented_control(
                "Sumber sampel", ["Upload audio", "YouTube"],
                default="Upload audio", key="vo_sample_source",
            )
            if source_kind == "Upload audio":
                upload = st.file_uploader(
                    "Upload sampel suara",
                    type=["wav", "mp3", "m4a", "ogg", "flac"],
                    key="vo_clone_upload",
                    help="Gunakan rekaman bersih. Sistem mengambil 30 detik "
                         "pertama agar proses lebih cepat.",
                )
            else:
                youtube_url = st.text_input(
                    "Link YouTube",
                    placeholder="https://www.youtube.com/watch?v=...",
                    key="vo_clone_youtube",
                )
                col_start, col_duration = st.columns(2)
                with col_start:
                    start_seconds = st.number_input(
                        "Mulai detik", min_value=0.0, value=0.0,
                        key="vo_clone_start")
                with col_duration:
                    sample_seconds = st.number_input(
                        "Durasi sampel", min_value=5.0, max_value=120.0,
                        value=30.0, key="vo_clone_duration")

            save_voice = st.checkbox(
                "Simpan hasil clone sebagai pilihan suara", value=True,
                key="vo_save_clone",
            )
            if save_voice:
                voice_name = st.text_input(
                    "Nama suara", placeholder="Contoh: Suara Rudi",
                    key="vo_clone_name",
                )
            consent = st.checkbox(
                "Saya memiliki izin menggunakan suara ini.",
                key="vo_clone_consent",
            )

with st.container(border=True):
    st.subheader("2. Generate voice over")
    st.caption(f"Naskah: {len(naskah):,} karakter. Hasil akan disimpan ke "
               f"`{vo_mp3.name}` dan `{vo_srt.name}`.")

    if st.button("Generate VO", icon=":material/mic:", type="primary",
                 use_container_width=True):
        error = ""
        log = ""

        if voice_mode == "Voice clone" and clone_api_problem:
            error = "Layanan voice clone belum terhubung."
        elif voice_mode == "Voice clone" and clone_source == "Buat clone baru":
            if upload is None and not youtube_url.strip():
                error = "Upload sampel audio atau isi link YouTube."
            elif not consent:
                error = "Centang persetujuan penggunaan suara."
            elif save_voice and not voice_name.strip():
                error = "Isi nama suara yang akan disimpan."

        if error:
            st.error(error)
        elif voice_mode == "Suara bawaan":
            with st.spinner("Membuat voice over..."):
                if builtin_choice == "Rudi Documenter (gaya narasi)":
                    return_code, log = runner.run([
                        "pipeline/vo_clone.py", "--naskah", str(naskah_file),
                        "--out-mp3", str(vo_mp3), "--out-srt", str(vo_srt),
                        "--preset", "homo_sapiens",
                    ])
                else:
                    voice_id = {
                        "Ardi (laki-laki)": "id-ID-ArdiNeural",
                        "Gadis (perempuan)": "id-ID-GadisNeural",
                    }[builtin_choice]
                    return_code, log = runner.run([
                        "make_vo.py", "--naskah", str(naskah_file),
                        "--out-mp3", str(vo_mp3), "--out-srt", str(vo_srt),
                        "--voice", voice_id, "--rate", rate,
                    ])
            if return_code:
                st.error("Generate VO gagal. Lihat log di bawah.")
            else:
                st.success("Voice over selesai dibuat.")
                st.rerun()
        else:
            progress = st.progress(0, text="Mengirim job voice clone...")
            status_box = st.empty()
            job_id = ""
            try:
                if clone_source == "Pakai suara tersimpan":
                    response = requests.post(
                        f"{clone_api}/api/jobs",
                        json={"text": naskah, "language": "id",
                              "consent": True,
                              "voice_id": selected_voice["id"]},
                        timeout=60,
                    )
                elif upload is not None:
                    response = requests.post(
                        f"{clone_api}/api/jobs/upload",
                        data={"text": naskah, "language": "id",
                              "consent": "true"},
                        files={"upload": (upload.name, upload.getvalue(),
                                           upload.type or "application/octet-stream")},
                        timeout=120,
                    )
                else:
                    response = requests.post(
                        f"{clone_api}/api/jobs",
                        json={"youtube_url": youtube_url.strip(),
                              "start_seconds": start_seconds,
                              "duration_seconds": sample_seconds,
                              "text": naskah, "language": "id",
                              "consent": True},
                        timeout=60,
                    )

                if not response.ok:
                    raise RuntimeError(api_error(response))
                job_id = response.json()["id"]
                success, log = wait_for_clone(job_id, progress, status_box)
                if not success:
                    raise RuntimeError(log)

                download_clone_results(job_id)
                if clone_source == "Buat clone baru" and save_voice:
                    save_response = requests.post(
                        f"{clone_api}/api/jobs/{job_id}/save-voice",
                        data={"nama": voice_name.strip()}, timeout=30)
                    if not save_response.ok:
                        status_box.warning(
                            "Audio berhasil dibuat, tetapi suara tidak tersimpan: "
                            + api_error(save_response))
                    else:
                        status_box.success(
                            f"Suara '{voice_name.strip()}' tersimpan dan dapat "
                            "dipilih pada generate berikutnya.")

                progress.progress(100, text="100% — selesai")
                st.success("Voice over clone selesai dibuat.")
            except (requests.RequestException, RuntimeError) as exc:
                st.error(f"Generate voice clone gagal: {exc}")
            finally:
                if job_id:
                    try:
                        requests.delete(f"{clone_api}/api/jobs/{job_id}",
                                        timeout=30)
                    except requests.RequestException:
                        pass

        if log:
            with st.expander("Log generate"):
                st.code(log[-6000:])

if vo_mp3.exists():
    with st.container(border=True):
        st.subheader("Hasil")
        st.audio(str(vo_mp3))
        st.caption(
            f"{vo_mp3.stat().st_size:,} bytes — diperbarui "
            f"{time.strftime('%d/%m/%Y %H:%M', time.localtime(vo_mp3.stat().st_mtime))}"
        )
        col_mp3, col_srt = st.columns(2)
        with col_mp3:
            st.download_button("Unduh vo.mp3", vo_mp3.read_bytes(),
                               file_name="vo.mp3", use_container_width=True)
        with col_srt:
            if vo_srt.exists():
                st.download_button("Unduh vo.srt", vo_srt.read_bytes(),
                                   file_name="vo.srt", use_container_width=True)

if vo_srt.exists():
    with st.expander("Pratinjau subtitle"):
        st.code("\n".join(vo_srt.read_text(
            encoding="utf-8").splitlines()[:20]))
