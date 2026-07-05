import streamlit st
import pandas as pd
from datetime import datetime, date
import psycopg2
from sqlalchemy import create_engine

st.set_page_config(page_title="MESEM Süreç Takip Otomasyonu (Hızlı Web)", layout="wide")

st.markdown("""
    <style>
    html, body, [data-testid="stWidgetLabel"], .stSelectbox, .stTextInput, .stTextArea, .stButton, p, span, label, .stRadio, .stNumberInput {
        font-size: 19px !important;
    }
    h1 { font-size: 36px !important; font-weight: bold !important; }
    h2 { font-size: 30px !important; font-weight: bold !important; color: #1E3A8A !important; }
    h3 { font-size: 24px !important; font-weight: bold !important; }
    [data-testid="stSidebar"] { min-width: 320px !important; }
    [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th { font-size: 17px !important; }
    </style>
""", unsafe_allow_html=True)

# --- BULUT BAĞLANTISI VE 10 SN ZAMAN AŞIMLI ÖN BELLEK (CACHE) MİMARİSİ ---
@st.cache_resource
def get_engine():
    return create_engine(st.secrets["DATABASE_URL"], pool_pre_ping=True, pool_size=10, max_overflow=20)

def get_connection():
    return psycopg2.connect(st.secrets["DATABASE_URL"])

engine = get_engine()

# SİHİRLİ DOKUNUŞ: Masaüstü güncellemelerini algılaması için cache'e 10 saniye ömür (ttl) biçildi.
@st.cache_data(ttl=10, show_spinner=False)
def verileri_getir(sorgu):
    return pd.read_sql_query(sorgu, engine)

def yas_hesapla(dogum_tarihi):
    bugun = date.today()
    return bugun.year - dogum_tarihi.year - ((bugun.month, bugun.day) < (dogum_tarihi.month, dogum_tarihi.day))

if "reset_sayaci" not in st.session_state: st.session_state.reset_sayaci = 0

st.sidebar.title("🛠️ MESEM Bulut Merkezi")
st.sidebar.success("⚡ Turbo Önbellek & Soft Delete Aktif")

menu = st.sidebar.radio("Lütfen bir bölüm seçin:", ("Genel Durum Paneli", "Öğrenci Bilgileri", "İşletme Bilgileri", "Eşleştirme ve Süreç Takibi"))

if menu == "Genel Durum Paneli":
    st.header("📊 MESEM Genel Durum Paneli")
    
    sorgu_kpi = """
        SELECT 
            COUNT(*) as toplam,
            COUNT(*) FILTER (WHERE mevcut_durum = 'Beklemede') as beklemede,
            COUNT(*) FILTER (WHERE mevcut_durum = 'Sözleşme İmzalandı (Yerleşti)') as yerlesen
        FROM ogrenciler WHERE silindi = 0
    """
    df_kpi = verileri_getir(sorgu_kpi)
    
    kpi1, kpi2, kpi3 = st.columns(3)
    with kpi1: st.metric("👥 Toplam Kayıtlı Aday", int(df_kpi["toplam"].iloc[0]))
    with kpi2: st.metric("⏳ İşletme Arayan", int(df_kpi["beklemede"].iloc[0]))
    with kpi3: st.metric("✅ Yerleşen / Sözleşmeli", int(df_kpi["yerlesen"].iloc[0]))
    
    st.markdown("---")
    st.subheader("🔍 Alanlara Göre Eşleşme Bekleyen Arz / Talep Havuzu")
    col_rapor1, col_rapor2 = st.columns(2)
    alanlar = ["Muhasebe ve Finansman", "Büro Yönetimi"]
    
    df_arz_toplu = verileri_getir("SELECT alan_dal, COUNT(*) as sayi FROM ogrenciler WHERE mevcut_durum='Beklemede' AND silindi=0 GROUP BY alan_dal")
    df_talep_toplu = verileri_getir("SELECT talep_edilen_alan, COALESCE(SUM(kontenjan), 0) as toplam FROM isletme_talepleri WHERE silindi=0 GROUP BY talep_edilen_alan")
    df_yerlesen_toplu = verileri_getir("SELECT o.alan_dal, COUNT(*) as sayi FROM eslesmeler e JOIN ogrenciler o ON e.ogrenci_id = o.ogrenci_id WHERE e.surec_durumu='Sözleşme İmzalandı (Yerleşti)' AND e.silindi=0 AND o.silindi=0 GROUP BY o.alan_dal")

    with col_rapor1:
        st.markdown("### ⏳ İşletme Bekleyen Öğrenciler")
        for alan in alanlar:
            filtre = df_arz_toplu[df_arz_toplu['alan_dal'] == alan]
            sayi = int(filtre['sayi'].iloc[0]) if not filtre.empty else 0
            st.info(f"**{alan}:** {sayi} Öğrenci atama bekliyor.")
    with col_rapor2:
        st.markdown("### 🏢 Öğrenci Arayan İşletmeler")
        for alan in alanlar:
            t_filtre = df_talep_toplu[df_talep_toplu['talep_edilen_alan'] == alan]
            y_filtre = df_yerlesen_toplu[df_yerlesen_toplu['alan_dal'] == alan]
            
            toplam_kontenjan = int(t_filtre['toplam'].iloc[0]) if not t_filtre.empty else 0
            yerlesen_kontenjan = int(y_filtre['sayi'].iloc[0]) if not y_filtre.empty else 0
            net_acik = max(0, toplam_kontenjan - yerlesen_kontenjan)
            st.success(f"**{alan}:** Toplam {net_acik} açık net kontenjan var.")

    st.markdown("---")
    st.subheader("🔍 Alan İstatistikleri (Güncel Atanan İşletme Detaylı)")
    for alan in alanlar:
        with st.expander(f"📘 {alan} Havuzu Detay Listesi"):
            sorgu_alan = f'''
                SELECT 
                    o.ad_soyad AS "Ad Soyad", o.obp AS "OBP", o.cinsiyet AS "Cinsiyet", o.mesem_sinifi AS "Sınıf", o.mevcut_durum AS "Durum",
                    COALESCE((SELECT i.isletme_adi FROM eslesmeler e JOIN isletmeler i ON e.isletme_id = i.isletme_id WHERE e.ogrenci_id = o.ogrenci_id AND e.silindi=0 ORDER BY e.islem_id DESC LIMIT 1), 'Atanmadı') AS "Yönlendirildiği İşletme"
                FROM ogrenciler o WHERE o.alan_dal = '{alan}' AND o.silindi = 0
            '''
            st.dataframe(verileri_getir(sorgu_alan), width='stretch', hide_index=True)

elif menu == "Öğrenci Bilgileri":
    st.header("👨‍🎓 Öğrenci İşlemleri Merkezi")
    conn = get_connection()
    sekme_listele, sekme_ekle = st.tabs(["📋 Öğrenci Havuzu & Yönetimi", "🏢 Yeni Öğrenci Ekle"])
    
    with sekme_ekle:
        gelis_sekli = st.radio("Öğrencinin Geldiği Yer", ["Kendi Okulumuzdan (TOKİ Yahya Kemal MTAL)", "Başka Okuldan Geliyor"], key=f"frm_gelis_{st.session_state.reset_sayaci}")
        ogretmen_notu = st.text_area("Öğretmen Görüşleri / Özellikleri", key=f"frm_not_{st.session_state.reset_sayaci}") if "Kendi" in gelis_sekli else ""
        
        st.markdown("---")
        ad_soyad = st.text_input("Öğrencinin Adı ve Soyadı", key=f"frm_ad_{st.session_state.reset_sayaci}")
        col_c, col_o = st.columns(2)
        with col_c: cinsiyet = st.selectbox("Cinsiyeti", ["Erkek", "Kız"], key=f"frm_cin_{st.session_state.reset_sayaci}")
        with col_o: obp = st.number_input("OBP Puanı", min_value=0.0, max_value=100.0, step=0.1, key=f"frm_obp_{st.session_state.reset_sayaci}")
        
        dogum_tarihi = st.date_input("Doğum Tarihi", value=date(date.today().year - 15, 1, 1), format="DD/MM/YYYY", key=f"frm_dt_{st.session_state.reset_sayaci}")
        yas = yas_hesapla(dogum_tarihi)
        if yas < 14: st.error("⚠️ Öğrenci 14 yaşından küçük!")
        
        orgun_gecmisi = st.selectbox("Örgün Durumu", ["9. Sınıf - Sınıf Tekrarına Kaldı", "9. Sınıf - Başarılı (10'a Geçti)", "10. Sınıf - Sınıf Tekrarına Kaldı", "10. Sınıf - Başarılı (11'e Geçti)", "11. Sınıf (Terk)", "12. Sınıf (Terk)"], key=f"frm_orgun_{st.session_state.reset_sayaci}")
        mesem_sinifi = st.selectbox("MESEM Sınıfı", ["9. Sınıf", "10. Sınıf", "11. Sınıf", "12. Sınıf"], index=1, key=f"frm_sinif_{st.session_state.reset_sayaci}")
        alan_dal = st.selectbox("Yönlendirileceği Alan", ["Muhasebe ve Finansman", "Büro Yönetimi"], key=f"frm_alan_{st.session_state.reset_sayaci}")
        
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1: ogrenci_telefon = st.text_input("Öğrenci Tel", key=f"frm_tel_{st.session_state.reset_sayaci}")
        with col_t2: anne_telefon = st.text_input("Anne Tel", key=f"frm_anne_{st.session_state.reset_sayaci}")
        with col_t3: baba_telefon = st.text_input("Baba Tel", key=f"frm_baba_{st.session_state.reset_sayaci}")
        ogrenci_adresi = st.text_area("Öğrenci Adresi", key=f"frm_adr_{st.session_state.reset_sayaci}")
        
        if st.button("💾 Öğrenciyi Havuza Ekle"):
            if yas >= 14 and ad_soyad:
                cursor = conn.cursor()
                cursor.execute('''INSERT INTO ogrenciler (ad_soyad, cinsiyet, dogum_tarihi, gelis_sekli, orgun_gecmisi, alan_dal, mesem_sinifi, obp, ogrenci_telefon, anne_telefon, baba_telefon, ogrenci_adresi, ogretmen_notu, silindi, senkronize_edildi) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 1)''', (ad_soyad, cinsiyet, dogum_tarihi.strftime("%Y-%m-%d"), gelis_sekli, orgun_gecmisi, alan_dal, mesem_sinifi, obp, ogrenci_telefon, anne_telefon, baba_telefon, ogrenci_adresi, ogretmen_notu))
                conn.commit(); cursor.close(); verileri_getir.clear()
                st.success(f"🎉 {ad_soyad} başarıyla buluta eklendi!")
                st.session_state.reset_sayaci += 1
                st.rerun()

    with sekme_listele:
        st.dataframe(verileri_getir('SELECT ogrenci_id AS "ID", ad_soyad AS "Ad Soyad", obp AS "OBP", alan_dal AS "Alan", mevcut_durum AS "Durum" FROM ogrenciler WHERE silindi=0 ORDER BY ogrenci_id DESC'), width='stretch', hide_index=True)
        st.markdown("---")
        df_o_list = verileri_getir("SELECT ogrenci_id, ad_soyad FROM ogrenciler WHERE silindi=0 ORDER BY ad_soyad ASC")
        if not df_o_list.empty:
            secenekler = ["Lütfen Seçiniz..."] + df_o_list['ad_soyad'].tolist()
            o_secim = st.selectbox("İncelemek, Güncellemek veya Silmek İstediğiniz Öğrenci:", secenekler, key=f"guncelle_o_secim_{st.session_state.reset_sayaci}")
            if o_secim != "Lütfen Seçiniz...":
                o_id = df_o_list.loc[df_o_list['ad_soyad'] == o_secim, 'ogrenci_id'].values[0]
                o_veri = verileri_getir(f"SELECT * FROM ogrenciler WHERE ogrenci_id = {o_id}").iloc[0]
                with st.form("o_duz_form"):
                    y_ad = st.text_input("Adı Soyadı", o_veri['ad_soyad'])
                    y_obp = st.number_input("OBP", value=float(o_veri['obp']) if pd.notnull(o_veri['obp']) else 50.0)
                    col_tel_o1, col_tel_o2, col_tel_o3 = st.columns(3)
                    with col_tel_o1: y_o_tel = st.text_input("Öğrenci Tel", o_veri['ogrenci_telefon'] or "")
                    with col_tel_o2: y_o_anne = st.text_input("Anne Tel", o_veri['anne_telefon'] or "")
                    with col_tel_o3: y_o_baba = st.text_input("Baba Tel", o_veri['baba_telefon'] or "")
                    y_durum = st.selectbox("Durumu", ["Beklemede", "Görüşmeye Gönderildi", "Sözleşme İmzalandı (Yerleşti)"], index=["Beklemede", "Görüşmeye Gönderildi", "Sözleşme İmzalandı (Yerleşti)"].index(o_veri['mevcut_durum']))
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.form_submit_button("📝 Güncelle"):
                            cursor = conn.cursor()
                            cursor.execute("UPDATE ogrenciler SET ad_soyad=%s, obp=%s, ogrenci_telefon=%s, anne_telefon=%s, baba_telefon=%s, mevcut_durum=%s WHERE ogrenci_id=%s", (y_ad, y_obp, y_o_tel, y_o_anne, y_o_baba, y_durum, int(o_id)))
                            conn.commit(); cursor.close(); verileri_getir.clear()
                            st.session_state.reset_sayaci += 1
                            st.success("Güncellendi!"); st.rerun()
                    with c2:
                        if st.form_submit_button("❌ SİSTEMDEN SİL (Gizle)"):
                            cursor = conn.cursor()
                            cursor.execute("UPDATE ogrenciler SET silindi=1 WHERE ogrenci_id=%s", (int(o_id),))
                            cursor.execute("UPDATE eslesmeler SET silindi=1 WHERE ogrenci_id=%s", (int(o_id),))
                            conn.commit(); cursor.close(); verileri_getir.clear()
                            st.session_state.reset_sayaci += 1
                            st.warning("Öğrenci sistemden silindi!"); st.rerun()
    conn.close()

elif menu == "İşletme Bilgileri":
    st.header("🏢 İşletme İşlemleri Merkezi")
    conn = get_connection()
    sekme_i_listele, sekme_i_ekle = st.tabs(["📋 İşletme Havuzu & Yönetimi", "🏢 Yeni İşletme Ekle"])
    
    with sekme_i_listele:
        st.dataframe(verileri_getir('SELECT isletme_id AS "ID", isletme_adi AS "İşletme Adı", yetkili_kisi AS "Yetkili", isletme_telefon AS "Telefon" FROM isletmeler WHERE silindi=0 ORDER BY isletme_id DESC'), width='stretch', hide_index=True)
        st.markdown("---")
        df_i_list = verileri_getir("SELECT isletme_id, isletme_adi FROM isletmeler WHERE silindi=0 ORDER BY isletme_adi ASC")
        if not df_i_list.empty:
            secenekler_i = ["Lütfen Seçiniz..."] + df_i_list['isletme_adi'].tolist()
            i_secim = st.selectbox("İncelemek, Güncellemek veya Silmek İstediğiniz İşletme:", secenekler_i, key=f"guncelle_i_secim_{st.session_state.reset_sayaci}")
            if i_secim != "Lütfen Seçiniz...":
                i_id = df_i_list.loc[df_i_list['isletme_adi'] == i_secim, 'isletme_id'].values[0]
                i_veri = verileri_getir(f"SELECT * FROM isletmeler WHERE isletme_id = {i_id}").iloc[0]
                with st.form("i_duzenleme_formu"):
                    y_i_ad = st.text_input("İşletme Adı", i_veri['isletme_adi'])
                    y_i_adr = st.text_area("İşletme Çalışma Adresi", i_veri['isletme_adresi'] or "")
                    
                    st.markdown("#### Yetkili Bilgileri")
                    c_y1, c_y2 = st.columns(2)
                    with c_y1:
                        y_i_kisi = st.text_input("Yetkili Adı Soyadı", i_veri['yetkili_kisi'] or "")
                        y_i_tel = st.text_input("Yetkili Telefonu", i_veri['yetkili_telefon'] or "")
                    with c_y2:
                        y_i_unv = st.text_input("Yetkili Görevi", i_veri['yetkili_unvani'] or "")
                        y_i_mail = st.text_input("Yetkili Mail", i_veri['yetkili_mail'] or "")
                    y_i_not = st.text_area("Özel Talepler / İstekler", i_veri['ozel_talepler'] or "")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.form_submit_button("📝 Güncelle"):
                            cursor = conn.cursor()
                            cursor.execute("UPDATE isletmeler SET isletme_adi=%s, isletme_adresi=%s, yetkili_kisi=%s, yetkili_telefon=%s, yetkili_unvani=%s, yetkili_mail=%s, ozel_talepler=%s WHERE isletme_id=%s", (y_i_ad, y_i_adr, y_i_kisi, y_i_tel, y_i_unv, y_i_mail, y_i_not, int(i_id)))
                            conn.commit(); cursor.close(); verileri_getir.clear()
                            st.session_state.reset_sayaci += 1
                            st.success("İşletme güncellendi!"); st.rerun()
                    with c2:
                        if st.form_submit_button("❌ SİSTEMDEN SİL"):
                            cursor = conn.cursor()
                            cursor.execute("UPDATE isletmeler SET silindi=1 WHERE isletme_id=%s", (int(i_id),))
                            cursor.execute("UPDATE isletme_talepleri SET silindi=1 WHERE isletme_id=%s", (int(i_id),))
                            cursor.execute("UPDATE eslesmeler SET silindi=1 WHERE isletme_id=%s", (int(i_id),))
                            conn.commit(); cursor.close(); verileri_getir.clear()
                            st.session_state.reset_sayaci += 1
                            st.warning("İşletme silindi!"); st.rerun()

    with sekme_i_ekle:
        isletme_adi = st.text_input("İşletme Adı", key=f"i_adi_{st.session_state.reset_sayaci}")
        isletme_adresi = st.text_area("İşletme Çalışma Adresi", key=f"i_adr_{st.session_state.reset_sayaci}")
        isletme_telefon = st.text_input("İşletme Sabit Tel", key=f"i_tel_{st.session_state.reset_sayaci}")
        
        st.markdown("### 🧑‍💼 Yetkili ve İletişim Bilgileri")
        c_e1, c_e2 = st.columns(2)
        with c_e1:
            yetkili_kisi = st.text_input("İrtibat Kişisi (Yetkili Adı)", key=f"i_ykisi_{st.session_state.reset_sayaci}")
            yetkili_telefon = st.text_input("Yetkili İletişim Numarası", key=f"i_ytel_{st.session_state.reset_sayaci}")
        with c_e2:
            yetkili_unvani = st.text_input("Yetkilinin Görevi", key=f"i_yunv_{st.session_state.reset_sayaci}")
            yetkili_mail = st.text_input("Yetkili Mail", key=f"i_ymail_{st.session_state.reset_sayaci}")
            
        ozel_talepler = st.text_area("İşletmenin Özel İstekleri (Örn: Sadece 12. sınıf erkek öğrenci vs.)", key=f"i_not_{st.session_state.reset_sayaci}")
        
        st.markdown("### 📊 Kontenjan Talebi")
        col_m, col_b = st.columns(2)
        with col_m: k_muh = st.number_input("Muhasebe Kontenjanı", min_value=0, key=f"i_muh_{st.session_state.reset_sayaci}")
        with col_b: k_bur = st.number_input("Büro Kontenjanı", min_value=0, key=f"i_bur_{st.session_state.reset_sayaci}")
        
        if st.button("🏢 İşletmeyi Ekle"):
            if isletme_adi:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO isletmeler (isletme_adi, isletme_adresi, isletme_telefon, yetkili_kisi, yetkili_telefon, yetkili_unvani, yetkili_mail, ozel_talepler, silindi, senkronize_edildi) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, 1) RETURNING isletme_id", (isletme_adi, isletme_adresi, isletme_telefon, yetkili_kisi, yetkili_telefon, yetkili_unvani, yetkili_mail, ozel_talepler))
                isletme_id = cursor.fetchone()[0]
                if k_muh > 0: cursor.execute("INSERT INTO isletme_talepleri (isletme_id, talep_edilen_alan, kontenjan, silindi, senkronize_edildi) VALUES (%s, 'Muhasebe ve Finansman', %s, 0, 1)", (isletme_id, k_muh))
                if k_bur > 0: cursor.execute("INSERT INTO isletme_talepleri (isletme_id, talep_edilen_alan, kontenjan, silindi, senkronize_edildi) VALUES (%s, 'Büro Yönetimi', %s, 0, 1)", (isletme_id, k_bur))
                conn.commit(); cursor.close(); verileri_getir.clear()
                st.success("İşletme buluta kaydedildi!")
                st.session_state.reset_sayaci += 1
                st.rerun()
    conn.close()

elif menu == "Eşleştirme ve Süreç Takibi":
    st.header("🤝 Akıllı Süreç Yönetimi")
    conn = get_connection()
    df_ogrenciler = verileri_getir("SELECT ogrenci_id, ad_soyad, alan_dal FROM ogrenciler WHERE mevcut_durum = 'Beklemede' AND silindi=0")
    
    if df_ogrenciler.empty:
        st.info("Bekleyen aday öğrenci yok.")
    else:
        ogrenci_secimi = st.selectbox("Öğrenciyi Seçin", df_ogrenciler['ad_soyad'].tolist())
        secili_id = df_ogrenciler.loc[df_ogrenciler['ad_soyad'] == ogrenci_secimi, 'ogrenci_id'].values[0]
        secili_alan = df_ogrenciler.loc[df_ogrenciler['ad_soyad'] == ogrenci_secimi, 'alan_dal'].values[0]
        
        sorgu_akilli = f'''
            SELECT i.isletme_id, i.isletme_adi 
            FROM isletmeler i 
            JOIN isletme_talepleri t ON i.isletme_id = t.isletme_id 
            WHERE t.talep_edilen_alan = '{secili_alan}' 
              AND i.silindi = 0 AND t.silindi = 0
              AND (t.kontenjan - (
                  SELECT COUNT(*) FROM eslesmeler e 
                  WHERE e.isletme_id = i.isletme_id 
                    AND e.surec_durumu = 'Sözleşme İmzalandı (Yerleşti)' AND e.silindi = 0
              )) > 0
        '''
        df_isletmeler = verileri_getir(sorgu_akilli)
        
        if df_isletmeler.empty: st.error(f"🚨 {secili_alan} için açık kontenjanı kalan işletme yok!")
        else:
            with st.form("eslestirme_formu"):
                isletme_secimi = st.selectbox("Uygun İşletmeler", df_isletmeler['isletme_adi'].tolist())
                surec_durumu = st.selectbox("Süreç Durumu", ["Görüşmeye Gönderildi", "Reddedildi", "Sözleşme İmzalandı (Yerleşti)"])
                islem_tarihi = st.date_input("İşlem Tarihi", format="DD/MM/YYYY")
                
                if st.form_submit_button("🔄 Kaydet"):
                    secilen_i_id = df_isletmeler.loc[df_isletmeler['isletme_adi'] == isletme_secimi, 'isletme_id'].values[0]
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO eslesmeler (ogrenci_id, isletme_id, surec_durumu, islem_tarihi, silindi, senkronize_edildi) VALUES (%s, %s, %s, %s, 0, 1)", (int(secili_id), int(secilen_i_id), surec_durumu, islem_tarihi))
                    yeni_statu = "Beklemede" if "Reddedildi" in surec_durumu else surec_durumu
                    cursor.execute("UPDATE ogrenciler SET mevcut_durum = %s WHERE ogrenci_id = %s", (yeni_statu, int(secili_id)))
                    conn.commit(); cursor.close(); verileri_getir.clear()
                    st.success("Süreç bulut veri tabanına kaydedildi!"); st.rerun()

    st.markdown("---")
    st.subheader("📋 Geçmiş Eşleşmeler ve Süreç Güncelleme")
    df_eslesmeler = verileri_getir("SELECT e.islem_id, o.ad_soyad AS ogrenci, i.isletme_adi AS isletme, e.surec_durumu, e.ogrenci_id FROM eslesmeler e JOIN ogrenciler o ON e.ogrenci_id = o.ogrenci_id JOIN isletmeler i ON e.isletme_id = i.isletme_id WHERE e.silindi=0 ORDER BY e.islem_id DESC")
    
    if not df_eslesmeler.empty:
        st.dataframe(df_eslesmeler[['islem_id', 'ogrenci', 'isletme', 'surec_durumu']].rename(columns={'islem_id': 'No', 'ogrenci': 'Öğrenci', 'isletme': 'İşletme', 'surec_durumu': 'Durum'}), width='stretch', hide_index=True)
        st.markdown("---")
        secenekler_e = ["Lütfen Seçiniz..."] + [f"{row['islem_id']} - {row['ogrenci']} ({row['isletme']})" for _, row in df_eslesmeler.iterrows()]
        e_secim = st.selectbox("İncelemek veya Silmek İstediğiniz Kayıt:", secenekler_e, key=f"guncelle_e_secim_{st.session_state.reset_sayaci}")
        
        if e_secim != "Lütfen Seçiniz...":
            e_id = int(e_secim.split(" - ")[0])
            e_veri = df_eslesmeler[df_eslesmeler['islem_id'] == e_id].iloc[0]
            if st.button("❌ EŞLEŞMEYİ İPTAL ET / SİL"):
                cursor = conn.cursor()
                cursor.execute("UPDATE eslesmeler SET silindi=1 WHERE islem_id=%s", (int(e_id),))
                cursor.execute("UPDATE ogrenciler SET mevcut_durum='Beklemede' WHERE ogrenci_id=%s", (int(e_veri['ogrenci_id']),))
                conn.commit(); cursor.close(); verileri_getir.clear()
                st.session_state.reset_sayaci += 1
                st.warning("Eşleşme kaydı silindi!"); st.rerun()
    conn.close()
