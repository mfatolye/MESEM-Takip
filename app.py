import streamlit as st
import pandas as pd
from datetime import datetime, date
import psycopg2
from sqlalchemy import create_engine

# Sayfa genişlik ayarları
st.set_page_config(page_title="MESEM Süreç Takip Otomasyonu", layout="wide")

# --- Gelişmiş Tasarım (CSS) ---
st.markdown("""
    <style>
    html, body, [data-testid="stWidgetLabel"], .stSelectbox, .stTextInput, .stTextArea, .stButton, .stNumberInput, p, span, label, .stRadio {
        font-size: 19px !important;
    }
    h1 { font-size: 36px !important; font-weight: bold !important; }
    h2 { font-size: 30px !important; font-weight: bold !important; color: #1E3A8A !important; }
    h3 { font-size: 24px !important; font-weight: bold !important; }
    [data-testid="stSidebar"] { min-width: 320px !important; }
    [data-testid="stDataFrame"] td, [data-testid="stDataFrame"] th { font-size: 17px !important; }
    </style>
""", unsafe_allow_html=True)

# --- BULUT VERİ TABANI (POSTGRESQL) BAĞLANTILARI ---
@st.cache_resource
def get_engine():
    # Pandas ile tablo okumaları için SQLAlchemy motoru
    return create_engine(st.secrets["DATABASE_URL"])

def get_connection():
    # Kayıt ekleme, silme ve güncellemeler için Psycopg2
    return psycopg2.connect(st.secrets["DATABASE_URL"])

# Veri tabanı tablolarını bulutta otomatik oluşturma fonksiyonu
def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ayarlar (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            okul_adi TEXT,
            alanlar TEXT,
            senkronize_edildi INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS ogrenciler (
            ogrenci_id SERIAL PRIMARY KEY,
            ad_soyad TEXT NOT NULL,
            cinsiyet TEXT,
            dogum_tarihi DATE,
            gelis_sekli TEXT,
            orgun_gecmisi TEXT,
            alan_dal TEXT,
            mesem_sinifi TEXT,
            obp REAL,
            ogrenci_telefon TEXT,
            anne_telefon TEXT,
            baba_telefon TEXT,
            ogrenci_adresi TEXT,
            ogretmen_notu TEXT,
            mevcut_durum TEXT DEFAULT 'Beklemede',
            senkronize_edildi INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS isletmeler (
            isletme_id SERIAL PRIMARY KEY,
            isletme_adi TEXT NOT NULL,
            yetkili_kisi TEXT,
            yetkili_unvani TEXT,
            isletme_telefon TEXT,
            yetkili_telefon TEXT,
            yetkili_mail TEXT,
            mali_adres TEXT,
            isletme_adresi TEXT,
            servis_imkani INTEGER DEFAULT 0,
            usta_ogretici_belgesi INTEGER DEFAULT 0,
            ozel_talepler TEXT,
            senkronize_edildi INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS isletme_talepleri (
            talep_id SERIAL PRIMARY KEY,
            isletme_id INTEGER REFERENCES isletmeler(isletme_id) ON DELETE CASCADE,
            talep_edilen_alan TEXT,
            kontenjan INTEGER,
            senkronize_edildi INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS eslesmeler (
            islem_id SERIAL PRIMARY KEY,
            ogrenci_id INTEGER REFERENCES ogrenciler(ogrenci_id) ON DELETE CASCADE,
            isletme_id INTEGER REFERENCES isletmeler(isletme_id) ON DELETE CASCADE,
            surec_durumu TEXT,
            islem_tarihi DATE,
            senkronize_edildi INTEGER DEFAULT 0
        );
    """)
    cursor.execute("SELECT COUNT(*) FROM ayarlar")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO ayarlar (id, okul_adi, alanlar) VALUES (1, 'TOKİ Yahya Kemal Çok Programlı Anadolu Lisesi', 'Muhasebe ve Finansman, Büro Yönetimi')")
    conn.commit()
    cursor.close()
    conn.close()

try:
    init_db()
except Exception as e:
    st.error(f"Veri tabanı bağlantı hatası. Lütfen Secrets (Sırlar) ayarlarınızı kontrol edin. Detay: {e}")

def yas_hesapla(dogum_tarihi):
    bugun = date.today()
    return bugun.year - dogum_tarihi.year - ((bugun.month, bugun.day) < (dogum_tarihi.month, dogum_tarihi.day))

# --- MERKEZİ HAFIZA HAVUZU ---
for k in ["o_ad_soyad", "o_obp", "o_tel", "o_anne", "o_baba", "o_adr", "o_not", "i_adi", "i_adr", "i_kisi", "i_tel", "i_unv", "i_mail", "i_not"]:
    if k not in st.session_state: st.session_state[k] = ""
if "i_muh" not in st.session_state: st.session_state.i_muh = 0
if "i_bur" not in st.session_state: st.session_state.i_bur = 0
if "reset_sayaci" not in st.session_state: st.session_state.reset_sayaci = 0

engine = get_engine()

# --- YAN MENÜ ---
st.sidebar.title("🛠️ MESEM Yönetim Merkezi")
menu = st.sidebar.radio("Lütfen bir bölüm seçin:", ("Genel Durum Paneli", "Öğrenci Bilgileri", "İşletme Bilgileri", "Eşleştirme ve Süreç Takibi"))

# --- 1. GENEL DURUM PANELİ ---
if menu == "Genel Durum Paneli":
    st.header("📊 MESEM Genel Durum Paneli")
    
    kpi1, kpi2, kpi3 = st.columns(3)
    with kpi1: st.metric("👥 Toplam Kayıtlı Aday", int(pd.read_sql_query("SELECT COUNT(*) FROM ogrenciler", engine).iloc[0, 0]))
    with kpi2: st.metric("⏳ İşletme Arayan (Beklemede)", int(pd.read_sql_query("SELECT COUNT(*) FROM ogrenciler WHERE mevcut_durum = 'Beklemede'", engine).iloc[0, 0]))
    with kpi3: st.metric("✅ İşe Yerleşen / Sözleşmeli", int(pd.read_sql_query("SELECT COUNT(*) FROM ogrenciler WHERE mevcut_durum = 'Sözleşme İmzalandı (Yerleşti)'", engine).iloc[0, 0]))
    
    st.markdown("---")
    st.subheader("🔍 Alanlara Göre Eşleşme Bekleyen Arz / Talep Havuzu")
    col_rapor1, col_rapor2 = st.columns(2)
    alanlar = ["Muhasebe ve Finansman", "Büro Yönetimi"]
    
    with col_rapor1:
        st.markdown("### ⏳ İşletme Bekleyen Öğrenciler")
        for alan in alanlar:
            sayi = pd.read_sql_query(f"SELECT COUNT(*) FROM ogrenciler WHERE alan_dal='{alan}' AND mevcut_durum='Beklemede'", engine).iloc[0, 0]
            st.info(f"**{alan}:** {sayi} Öğrenci atama bekliyor.")
            
    with col_rapor2:
        st.markdown("### 🏢 Öğrenci Arayan İşletmeler")
        for alan in alanlar:
            talep = pd.read_sql_query(f"SELECT COALESCE(SUM(kontenjan), 0) FROM isletme_talepleri WHERE talep_edilen_alan='{alan}'", engine).iloc[0, 0]
            st.success(f"**{alan}:** Toplam {int(talep)} açık kontenjan var.")

    st.markdown("---")
    st.subheader("📁 Alan İstatistikleri (Güncel Atanan İşletme Detaylı)")
    for alan in alanlar:
        with st.expander(f"📘 {alan} Havuzu Detay Listesi"):
            sorgu_alan = f'''
                SELECT 
                    o.ad_soyad AS "Ad Soyad", o.obp AS "OBP", o.cinsiyet AS "Cinsiyet", o.mesem_sinifi AS "Sınıf", o.mevcut_durum AS "Durum",
                    COALESCE((SELECT i.isletme_adi FROM eslesmeler e JOIN isletmeler i ON e.isletme_id = i.isletme_id WHERE e.ogrenci_id = o.ogrenci_id ORDER BY e.islem_id DESC LIMIT 1), 'Atanmadı') AS "Yönlendirildiği İşletme"
                FROM ogrenciler o WHERE o.alan_dal = '{alan}'
            '''
            st.dataframe(pd.read_sql_query(sorgu_alan, engine), width='stretch', hide_index=True)

# --- 2. ÖĞRENCİ BİLGİLERİ ---
elif menu == "Öğrenci Bilgileri":
    st.header("👨‍🎓 Öğrenci İşlemleri Merkezi")
    sekme_listele, sekme_ekle = st.tabs(["📋 Öğrenci Havuzu & Yönetimi", "➕ Yeni Öğrenci Ekle"])
    
    with sekme_ekle:
        st.subheader("➕ Yeni Aday Öğrenci Kaydı")
        gelis_sekli = st.radio("Öğrencinin Geldiği Yer", ["Kendi Okulumuzdan (TOKİ Yahya Kemal MTAL)", "Başka Okuldan Geliyor"], key=f"o_gelis_{st.session_state.reset_sayaci}")
        
        if "Kendi Okulumuzdan" in gelis_sekli:
            st.text_area("Öğretmen Görüşleri / Kişilik Özellikleri", key="o_not", placeholder="Örn: El becerisi iyi...")
        else:
            st.session_state.o_not = ""

        st.markdown("---")
        st.text_input("Öğrencinin Adı ve Soyadı", key="o_ad_soyad")
        col_c, col_o = st.columns(2)
        with col_c: cinsiyet = st.selectbox("Cinsiyeti", ["Erkek", "Kız"], key="o_cinsiyet")
        with col_o: st.number_input("Ortaöğretim Başarı Puanı (OBP)", min_value=0.0, max_value=100.0, step=0.1, key="o_obp")
        
        col_tarih, col_yas = st.columns(2)
        with col_tarih: dogum_tarihi = st.date_input("Doğum Tarihi", value=date(date.today().year - 15, 1, 1), min_value=date(1990, 1, 1), max_value=date.today(), format="DD/MM/YYYY", key="o_dogum")
        yas = yas_hesapla(st.session_state.o_dogum)
        with col_yas:
            st.markdown(f"<br>**Yaş:** {yas}", unsafe_allow_html=True)
            if yas < 14: st.error("⚠️ 14 yaşından küçük!")
            else: st.success("✅ Yaş uygun.")

        st.markdown("---")
        col_org, col_mes = st.columns(2)
        with col_org: st.selectbox("Örgün Son Durumu", ["9. Sınıf - Sınıf Tekrarına Kaldı", "9. Sınıf - Başarılı (10'a Geçti)", "10. Sınıf - Sınıf Tekrarına Kaldı", "10. Sınıf - Başarılı (11'e Geçti)", "11. Sınıf (Terk / Geçiş)", "12. Sınıf (Terk / Geçiş)"], key="o_orgun")
        with col_mes: st.selectbox("MESEM Sınıfı", ["9. Sınıf", "10. Sınıf", "11. Sınıf", "12. Sınıf"], index=1, key="o_sinif")
        st.selectbox("Yönlendirileceği Alan", ["Muhasebe ve Finansman", "Büro Yönetimi"], key="o_alan")
        
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1: st.text_input("Öğrenci Telefon No", key="o_tel")
        with col_t2: st.text_input("Anne Telefon No", key="o_anne")
        with col_t3: st.text_input("Baba Telefon No", key="o_baba")
        st.text_area("İkamet Adresi", key="o_adr")
        
        if st.button("💾 Öğrenciyi Havuza Ekle"):
            if yas < 14: st.error("Hata: Yaş sınırı!")
            elif not st.session_state.o_ad_soyad: st.warning("Lütfen öğrenci adı giriniz.")
            else:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO ogrenciler (ad_soyad, cinsiyet, dogum_tarihi, gelis_sekli, orgun_gecmisi, alan_dal, mesem_sinifi, obp, ogrenci_telefon, anne_telefon, baba_telefon, ogrenci_adresi, ogretmen_notu) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (st.session_state.o_ad_soyad, st.session_state.o_cinsiyet, st.session_state.o_dogum.strftime("%Y-%m-%d"), "Kendi Okulu" if "Kendi Okulumuzdan" in gelis_sekli else "Başka Okul", st.session_state.o_orgun, st.session_state.o_alan, st.session_state.o_sinif, st.session_state.o_obp, st.session_state.o_tel, st.session_state.o_anne, st.session_state.o_baba, st.session_state.o_adr, st.session_state.o_not))
                conn.commit()
                cursor.close(); conn.close()
                st.success(f"🎉 {st.session_state.o_ad_soyad} başarıyla eklendi!")
                
                st.session_state.o_ad_soyad = ""; st.session_state.o_tel = ""; st.session_state.o_anne = ""; st.session_state.o_baba = ""; st.session_state.o_adr = ""; st.session_state.o_not = ""
                st.session_state.reset_sayaci += 1
                st.rerun()

    with sekme_listele:
        st.dataframe(pd.read_sql_query('SELECT ogrenci_id AS "ID", ad_soyad AS "Ad Soyad", obp AS "OBP", alan_dal AS "Alan", mevcut_durum AS "Durum" FROM ogrenciler', engine), width='stretch', hide_index=True)
        st.markdown("---")
        
        df_o_list = pd.read_sql_query("SELECT ogrenci_id, ad_soyad FROM ogrenciler", engine)
        secenekler = ["Lütfen Seçiniz..."] + df_o_list['ad_soyad'].tolist()
        
        o_secim = st.selectbox("İncelemek, Güncellemek veya Silmek İstediğiniz Öğrenci:", secenekler, key=f"guncelle_o_secim_{st.session_state.reset_sayaci}")
        
        if o_secim != "Lütfen Seçiniz...":
            o_id = df_o_list.loc[df_o_list['ad_soyad'] == o_secim, 'ogrenci_id'].values[0]
            o_veri = pd.read_sql_query(f"SELECT * FROM ogrenciler WHERE ogrenci_id = {o_id}", engine).iloc[0]
            
            with st.form("o_duz_form"):
                y_ad = st.text_input("Adı Soyadı", o_veri['ad_soyad'])
                y_obp = st.number_input("OBP", value=float(o_veri['obp']) if pd.notnull(o_veri['obp']) else 50.0)
                
                col_i1, col_i2, col_i3 = st.columns(3)
                with col_i1: y_tel = st.text_input("Öğrenci Tel", o_veri['ogrenci_telefon'] or "")
                with col_i2: y_anne = st.text_input("Anne Tel", o_veri['anne_telefon'] or "")
                with col_i3: y_baba = st.text_input("Baba Tel", o_veri['baba_telefon'] or "")
                
                y_durum = st.selectbox("Durumu", ["Beklemede", "Görüşmeye Gönderildi", "Sözleşme İmzalandı (Yerleşti)"], index=["Beklemede", "Görüşmeye Gönderildi", "Sözleşme İmzalandı (Yerleşti)"].index(o_veri['mevcut_durum']))
                
                c1, c2 = st.columns(2)
                with c1:
                    if st.form_submit_button("📝 Güncelle"):
                        conn = get_connection(); cursor = conn.cursor()
                        cursor.execute("UPDATE ogrenciler SET ad_soyad=%s, obp=%s, ogrenci_telefon=%s, anne_telefon=%s, baba_telefon=%s, mevcut_durum=%s WHERE ogrenci_id=%s", (y_ad, y_obp, y_tel, y_anne, y_baba, y_durum, int(o_id)))
                        conn.commit(); cursor.close(); conn.close()
                        st.session_state.reset_sayaci += 1
                        st.success("Güncellendi!"); st.rerun()
                with c2:
                    if st.form_submit_button("❌ SİSTEMDEN SİL"):
                        conn = get_connection(); cursor = conn.cursor()
                        cursor.execute("DELETE FROM ogrenciler WHERE ogrenci_id=%s", (int(o_id),))
                        conn.commit(); cursor.close(); conn.close()
                        st.session_state.reset_sayaci += 1
                        st.warning("Silindi!"); st.rerun()

# --- 3. İŞLETME BİLGİLERİ ---
elif menu == "İşletme Bilgileri":
    st.header("🏢 İşletme İşlemleri Merkezi")
    sekme_i_listele, sekme_i_ekle = st.tabs(["📋 İşletme Havuzu & Yönetimi", "🏢 Yeni İşletme Ekle"])
    
    with sekme_i_listele:
        st.dataframe(pd.read_sql_query('SELECT isletme_id AS "ID", isletme_adi AS "İşletme Adı", yetkili_kisi AS "Yetkili", yetkili_telefon AS "Yetkili Tel", isletme_adresi AS "Adres" FROM isletmeler', engine), width='stretch', hide_index=True)
        st.markdown("---")
        
        df_i_list = pd.read_sql_query("SELECT isletme_id, isletme_adi FROM isletmeler", engine)
        secenekler_i = ["Lütfen Seçiniz..."] + df_i_list['isletme_adi'].tolist()
        i_secim = st.selectbox("İncelemek, Güncellemek veya Silmek İstediğiniz İşletme:", secenekler_i, key=f"guncelle_i_secim_{st.session_state.reset_sayaci}")
        
        if i_secim != "Lütfen Seçiniz...":
            i_id = df_i_list.loc[df_i_list['isletme_adi'] == i_secim, 'isletme_id'].values[0]
            i_veri = pd.read_sql_query(f"SELECT * FROM isletmeler WHERE isletme_id = {i_id}", engine).iloc[0]
            
            with st.form("i_duzenleme_formu"):
                y_i_ad = st.text_input("İşletme Adı", i_veri['isletme_adi'])
                y_i_adr = st.text_area("İşletme Çalışma Adresi", i_veri['isletme_adresi'] or "")
                
                c_y1, c_y2 = st.columns(2)
                with c_y1:
                    y_i_kisi = st.text_input("Yetkili Adı Soyadı", i_veri['yetkili_kisi'] or "")
                    y_i_tel = st.text_input("Yetkili Telefonu", i_veri['yetkili_telefon'] or "")
                with c_y2:
                    y_i_unv = st.text_input("Yetkili Görevi", i_veri['yetkili_unvani'] or "")
                    y_i_mail = st.text_input("Yetkili Mail", i_veri['yetkili_mail'] or "")
                
                y_i_not = st.text_area("Özel Talepler", i_veri['ozel_talepler'] or "")
                
                c1, c2 = st.columns(2)
                with c1:
                    if st.form_submit_button("📝 Güncelle"):
                        conn = get_connection(); cursor = conn.cursor()
                        cursor.execute("UPDATE isletmeler SET isletme_adi=%s, isletme_adresi=%s, yetkili_kisi=%s, yetkili_unvani=%s, yetkili_telefon=%s, yetkili_mail=%s, ozel_talepler=%s WHERE isletme_id=%s", (y_i_ad, y_i_adr, y_i_kisi, y_i_unv, y_i_tel, y_i_mail, y_i_not, int(i_id)))
                        conn.commit(); cursor.close(); conn.close()
                        st.session_state.reset_sayaci += 1
                        st.success("Güncellendi!"); st.rerun()
                with c2:
                    if st.form_submit_button("❌ SİSTEMDEN SİL"):
                        conn = get_connection(); cursor = conn.cursor()
                        cursor.execute("DELETE FROM isletmeler WHERE isletme_id=%s", (int(i_id),))
                        conn.commit(); cursor.close(); conn.close()
                        st.session_state.reset_sayaci += 1
                        st.warning("Silindi!"); st.rerun()

    with sekme_i_ekle:
        st.subheader("İşletme Genel Bilgileri")
        st.text_input("İşletme Adı", key="i_adi")
        st.text_area("İşletme Çalışma Adresi", key="i_adr")
        
        st.subheader("İletişim ve Yetkili Bilgileri")
        c_y1, c_y2 = st.columns(2)
        with c_y1:
            st.text_input("Yetkili Kişi Adı Soyadı", key="i_kisi")
            st.text_input("Yetkili Telefon Numarası", key="i_tel")
        with c_y2:
            st.text_input("Yetkilinin Görevi / Unvanı", key="i_unv")
            st.text_input("Yetkili Mail Adresi", key="i_mail")
        
        st.text_area("Özel İstekler", key="i_not")
        
        st.markdown("### 📊 Bölüm Bazlı Kontenjan Talebi")
        col_m, col_b = st.columns(2)
        with col_m: st.number_input("Muhasebe Kontenjanı", min_value=0, step=1, key="i_muh")
        with col_b: st.number_input("Büro Yönetimi Kontenjanı", min_value=0, step=1, key="i_bur")
        
        if st.button("🏢 İşletmeyi Havuza Ekle"):
            if not st.session_state.i_adi: 
                st.warning("İşletme adı giriniz.")
            else:
                conn = get_connection(); cursor = conn.cursor()
                # PostgreSQL'de eklenen ID'yi almak için RETURNING kullanılır
                cursor.execute("INSERT INTO isletmeler (isletme_adi, isletme_adresi, yetkili_kisi, yetkili_unvani, yetkili_telefon, yetkili_mail, ozel_talepler) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING isletme_id", (st.session_state.i_adi, st.session_state.i_adr, st.session_state.i_kisi, st.session_state.i_unv, st.session_state.i_tel, st.session_state.i_mail, st.session_state.i_not))
                isletme_id = cursor.fetchone()[0]
                
                if st.session_state.i_muh > 0: cursor.execute("INSERT INTO isletme_talepleri (isletme_id, talep_edilen_alan, kontenjan) VALUES (%s, 'Muhasebe ve Finansman', %s)", (isletme_id, st.session_state.i_muh))
                if st.session_state.i_bur > 0: cursor.execute("INSERT INTO isletme_talepleri (isletme_id, talep_edilen_alan, kontenjan) VALUES (%s, 'Büro Yönetimi', %s)", (isletme_id, st.session_state.i_bur))
                conn.commit(); cursor.close(); conn.close()
                st.success("🏢 İşletme başarıyla eklendi!")
                
                for k in ["i_adi", "i_adr", "i_kisi", "i_tel", "i_unv", "i_mail", "i_not"]: st.session_state[k] = ""
                st.session_state.i_muh = 0; st.session_state.i_bur = 0
                st.session_state.reset_sayaci += 1
                st.rerun()

# --- 4. EŞLEŞTİRME VE SÜREÇ TAKİBİ ---
elif menu == "Eşleştirme ve Süreç Takibi":
    st.header("🤝 Akıllı Süreç Yönetimi ve Eşleştirme")
    df_ogrenciler = pd.read_sql_query("SELECT ogrenci_id, ad_soyad, alan_dal FROM ogrenciler WHERE mevcut_durum = 'Beklemede'", engine)
    
    if df_ogrenciler.empty:
        st.info("Şu anda işletme arayan (Beklemede statüsünde) aday öğrenci bulunmamaktadır.")
    else:
        ogrenci_secimi = st.selectbox("Eşleştirilecek Öğrenciyi Seçin", df_ogrenciler['ad_soyad'].tolist())
        secili_id = df_ogrenciler.loc[df_ogrenciler['ad_soyad'] == ogrenci_secimi, 'ogrenci_id'].values[0]
        secili_alan = df_ogrenciler.loc[df_ogrenciler['ad_soyad'] == ogrenci_secimi, 'alan_dal'].values[0]
        
        sorgu_akilli = f"SELECT DISTINCT i.isletme_id, i.isletme_adi FROM isletmeler i JOIN isletme_talepleri t ON i.isletme_id = t.isletme_id WHERE t.talep_edilen_alan = '{secili_alan}' AND t.kontenjan > 0"
        df_isletmeler = pd.read_sql_query(sorgu_akilli, engine)
        
        if df_isletmeler.empty: st.error(f"🚨 Uyarı: **{secili_alan}** alanından açık kontenjanı olan işletme yok!")
        else:
            with st.form("eslestirme_formu", clear_on_submit=True):
                isletme_secimi = st.selectbox("Adayın Bölümüne Uygun İşletmeler", df_isletmeler['isletme_adi'].tolist())
                surec_durumu = st.selectbox("Süreç Durumu", ["Görüşmeye Gönderildi", "Olumsuz Sonuçlandı / Reddedildi", "Sözleşme İmzalandı (Yerleşti)"])
                islem_tarihi = st.date_input("İşlem Tarihi", format="DD/MM/YYYY")
                
                if st.form_submit_button("🔄 Süreci Kaydet"):
                    secilen_i_id = df_isletmeler.loc[df_isletmeler['isletme_adi'] == isletme_secimi, 'isletme_id'].values[0]
                    conn = get_connection(); cursor = conn.cursor()
                    cursor.execute("INSERT INTO eslesmeler (ogrenci_id, isletme_id, surec_durumu, islem_tarihi) VALUES (%s, %s, %s, %s)", (int(secili_id), int(secilen_i_id), surec_durumu, islem_tarihi))
                    if surec_durumu == "Sözleşme İmzalandı (Yerleşti)":
                        cursor.execute("UPDATE isletme_talepleri SET kontenjan = kontenjan - 1 WHERE isletme_id = %s AND talep_edilen_alan = %s", (int(secilen_i_id), secili_alan))
                    yeni_ogrenci_statu = "Beklemede" if "Reddedildi" in surec_durumu else surec_durumu
                    cursor.execute("UPDATE ogrenciler SET mevcut_durum = %s WHERE ogrenci_id = %s", (yeni_ogrenci_statu, int(secili_id)))
                    conn.commit(); cursor.close(); conn.close()
                    st.success("✅ Kaydedildi!"); st.rerun()

    st.markdown("---")
    sorgu_liste = 'SELECT e.islem_id AS "İşlem No", o.ad_soyad AS "Öğrenci", i.isletme_adi AS "İşletme", e.surec_durumu AS "Durum" FROM eslesmeler e JOIN ogrenciler o ON e.ogrenci_id = o.ogrenci_id JOIN isletmeler i ON e.isletme_id = i.isletme_id ORDER BY e.islem_id DESC'
    st.dataframe(pd.read_sql_query(sorgu_liste, engine), width='stretch', hide_index=True)