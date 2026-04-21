from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3, hashlib, secrets, smtplib, os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date, timedelta
import json
from functools import wraps
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'kartnation_secret_key_2024')
DB_PATH = 'kartodromo.db'

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID', ''),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET', ''),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

EMAIL_CONFIG = {
    'SMTP_SERVER': 'smtp.gmail.com',
    'SMTP_PORT': 587,
    'EMAIL_USER': 'tucorreo@gmail.com',
    'EMAIL_PASS': 'tu_contrasena_app',
    'EMAIL_FROM_NAME': 'KARTNATION',
}

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        apellido TEXT DEFAULT '',
        fecha_nacimiento TEXT DEFAULT '',
        teléfono TEXT DEFAULT '',
        dni TEXT DEFAULT '',
        age INTEGER,
        experience_years INTEGER DEFAULT 0,
        karting_level TEXT DEFAULT 'Novato',
        races_completed INTEGER DEFAULT 0,
        best_lap_time TEXT DEFAULT '--:--',
        bio TEXT DEFAULT '',
        avatar_initial TEXT,
        is_admin INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS circuits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        location TEXT NOT NULL,
        lat REAL DEFAULT 0.0,
        lng REAL DEFAULT 0.0,
        address TEXT DEFAULT '',
        description TEXT,
        long_description TEXT,
        length_m INTEGER,
        max_speed_kmh INTEGER,
        track_type TEXT,
        difficulty TEXT,
        max_per_session INTEGER DEFAULT 12,
        price_per_session REAL DEFAULT 25.0,
        color TEXT DEFAULT '#FF4D00',
        emoji TEXT DEFAULT '🏁',
        website TEXT DEFAULT ''
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS kart_types (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        circuit_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        engine_cc INTEGER DEFAULT 0,
        description TEXT DEFAULT '',
        min_age INTEGER DEFAULT 0,
        price_per_session REAL DEFAULT 0.0,
        FOREIGN KEY (circuit_id) REFERENCES circuits(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        circuit_id INTEGER NOT NULL,
        kart_type_id INTEGER,
        booking_date TEXT NOT NULL,
        time_slot TEXT NOT NULL,
        status TEXT DEFAULT 'confirmed',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id),
        FOREIGN KEY (circuit_id) REFERENCES circuits(id),
        FOREIGN KEY (kart_type_id) REFERENCES kart_types(id),
        UNIQUE(user_id, circuit_id, booking_date, time_slot)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS manual_bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        circuit_id INTEGER NOT NULL,
        kart_type_id INTEGER,
        booking_date TEXT NOT NULL,
        time_slot TEXT NOT NULL,
        num_pilots INTEGER NOT NULL DEFAULT 1,
        contact_name TEXT NOT NULL,
        contact_phone TEXT,
        contact_email TEXT,
        notes TEXT DEFAULT '',
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (circuit_id) REFERENCES circuits(id),
        FOREIGN KEY (kart_type_id) REFERENCES kart_types(id),
        FOREIGN KEY (created_by) REFERENCES users(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS circuit_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        circuit_name TEXT NOT NULL,
        city TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS circuit_info (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER UNIQUE NOT NULL,
        display_name TEXT DEFAULT '',
        address TEXT DEFAULT '',
        city TEXT DEFAULT '',
        length_m INTEGER DEFAULT 0,
        max_per_session INTEGER DEFAULT 12,
        website TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        description TEXT DEFAULT '',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (account_id) REFERENCES circuit_accounts(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS circuit_schedule (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        weekday INTEGER NOT NULL,
        open_time TEXT DEFAULT '',
        close_time TEXT DEFAULT '',
        is_closed INTEGER DEFAULT 0,
        UNIQUE(account_id, weekday),
        FOREIGN KEY (account_id) REFERENCES circuit_accounts(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS circuit_schedule_override (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        override_date TEXT NOT NULL,
        open_time TEXT DEFAULT '',
        close_time TEXT DEFAULT '',
        is_closed INTEGER DEFAULT 0,
        reason TEXT DEFAULT '',
        UNIQUE(account_id, override_date),
        FOREIGN KEY (account_id) REFERENCES circuit_accounts(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS circuit_manual_bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        booking_date TEXT NOT NULL,
        time_slot TEXT NOT NULL,
        num_pilots INTEGER NOT NULL DEFAULT 1,
        contact_name TEXT NOT NULL,
        contact_phone TEXT DEFAULT '',
        contact_email TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (account_id) REFERENCES circuit_accounts(id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token TEXT UNIQUE NOT NULL,
        expires_at TIMESTAMP NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )''')

    # Add google_id column for OAuth users
    try:
        c.execute('ALTER TABLE users ADD COLUMN google_id TEXT')
    except: pass

    # Add columns to existing tables if missing
    for col, defval in [('is_admin','INTEGER DEFAULT 0'), ('website','TEXT'), ('address','TEXT')]:
        try:
            c.execute(f'ALTER TABLE users ADD COLUMN {col} {defval}')
        except: pass
        try:
            c.execute(f'ALTER TABLE circuits ADD COLUMN {col} {defval}')
        except: pass

    # Add price_per_session to circuit_info if missing
    try:
        c.execute("ALTER TABLE circuit_info ADD COLUMN price_per_session REAL DEFAULT 0.0")
    except: pass

    # Migrate kart_types: add price_per_session if missing (replaces price_extra)
    try:
        c.execute("ALTER TABLE kart_types ADD COLUMN price_per_session REAL DEFAULT 0.0")
    except: pass
    # Copy price_extra → price_per_session for existing rows, then we leave price_extra as-is
    try:
        c.execute("UPDATE kart_types SET price_per_session = price_extra WHERE price_per_session = 0.0 AND price_extra > 0.0")
    except: pass

    # Link circuit_accounts to circuits table
    try:
        c.execute('ALTER TABLE circuit_accounts ADD COLUMN linked_circuit_id INTEGER DEFAULT NULL')
    except: pass

    # Add lat/lng to circuits if missing
    try:
        c.execute('ALTER TABLE circuits ADD COLUMN lat REAL DEFAULT 0.0')
    except: pass
    try:
        c.execute('ALTER TABLE circuits ADD COLUMN lng REAL DEFAULT 0.0')
    except: pass

    # Add kart_mix_policy to circuits: 'all' = todos juntos, 'separate' = adulto separado de biplaza/junior
    try:
        c.execute("ALTER TABLE circuits ADD COLUMN kart_mix_policy TEXT DEFAULT 'all'")
    except: pass

    # Update coordinates for known circuits
    circuit_coords = {
        'Karting Calafat': (40.9265, 0.8374),
        'Karting Coma-Ruga': (41.1667, 1.5500),
        'Karting Vendrell': (41.2167, 1.5500),
        'Karting Calafat': (40.9265, 0.8374),
        'Gene Karting': (41.3043, 2.0108),
        'Indoor Karting Barcelona': (41.3799, 2.0435),
        'Karting Cardedeu': (41.6406, 2.3609),
        'Karting Castelloli - ParcMotor': (41.5167, 1.6833),
        'Karting Sallent': (41.8200, 1.8900),
        "Circuit d'Osona Karting": (41.9295, 2.2543),
    }
    for name, (lat, lng) in circuit_coords.items():
        c.execute('UPDATE circuits SET lat=?, lng=? WHERE name=?', (lat, lng, name))

    # New user fields — safe to run on existing DBs
    new_user_cols = [
        ('apellido', "TEXT DEFAULT ''"),
        ('fecha_nacimiento', "TEXT DEFAULT ''"),
        ('teléfono', "TEXT DEFAULT ''"),
        ('dni', "TEXT DEFAULT ''"),
    ]
    for col, defval in new_user_cols:
        try:
            c.execute(f'ALTER TABLE users ADD COLUMN {col} {defval}')
        except: pass

    try:
        c.execute('ALTER TABLE circuit_manual_bookings ADD COLUMN kart_type_id INTEGER')
    except: pass


    # Seed circuits
    c.execute('SELECT COUNT(*) FROM circuits')
    if c.fetchone()[0] == 0:
        circuits = [
            ('Gene Karting', 'Viladecans', 'Av. del Segle XXI, 6 (C.C. Vilamarina), 08840 Viladecans',
             'El karting indoor del piloto Marc Gene, en el CC Vilamarina',
             'Circuito indoor técnico de 500 metros con 8 curvas a derechas y 9 a izquierdas, con tramos de subida y bajada. Avanzado sistema de protección Protex. Avalado por el piloto de F1 Marc Gene, es uno de los kartings más modernos y completos de Cataluña. Incluye bar con vistas al circuito y sala de conferencias de 120 m2.',
             500, 60, 'Indoor', 'Intermedio', 10, 18.00, '#FF4D00', '🔥', 'https://barcelonagenekarting.com'),
            ('Indoor Karting Barcelona', 'Sant Feliu de Llobregat', 'Pol. Ind. El Pla, Ctra. Laurea Miro, 434, 08980 Sant Feliu de Llobregat',
             'El primer circuito indoor de España, el más avanzado de Europa',
             'Circuito cubierto de 500 metros con 10 curvas a derechas y 5 a izquierdas. Subidas, bajadas y curvas enlazadas que lo hacen muy técnico y divertido. Cronometraje profesional en todas las tandas con envio de tiempos por email. También dispone de bolera, Laser Tag y restaurante. A solo 11 km del centro de Barcelona.',
             500, 65, 'Indoor', 'Intermedio', 15, 20.00, '#00C4FF', '⚡', 'https://indoorkartingbarcelona.com'),
            ('Karting Cardedeu', 'Cardedeu', 'Ctra. Granollers a Sant Celoni (C-251), Km 5.300, 08440 Cardedeu',
             'Circuito técnico al aire libre a 35 km de Barcelona',
             'Pista outdoor de 750 metros de longitud y 8 metros de ancho con iluminación para disfrutar de dia y por la noche. Trazado técnico con curvas suaves y pendientes que atrae a pilotos de todos los niveles. Bar, vestuarios y zona de paddock. Frecuentemente disponible para sesiónes individuales y grupos privados.',
             750, 70, 'Outdoor', 'Intermedio', 12, 18.00, '#7CFF00', '🌿', 'https://www.kartingcardedeu.com'),
            ('Karting Castelloli - ParcMotor', 'Castelloli', 'Carretera Nacional IIa, Km 560, 08719 Castelloli',
             'El mejor karting de Cataluña, diseñado por Dani Pedrosa',
             'Espectacular circuito outdoor de 1.340 metros diseñado por el campeón del mundo Dani Pedrosa. Con cambios de rasante, curvas peraltadas y rectas de alta velocidad que simulan una pista de Formula 1. Flota de karts Sodikart 400cc de alta potencia perfectamente mantenidos. Complejo de 70.000 m2 con paintball, restaurante panorámico y Humor Amarillo. El preferido de los pilotos más exigentes.',
             1340, 95, 'Outdoor', 'Avanzado', 12, 25.00, '#FFD700', '🏆', 'https://www.parcmotorcastelloli.com'),
            ('Karting Sallent', 'Sallent', 'Ctra. C-16 km 58.5, 08650 Sallent',
             'El circuito de karts más largo de Cataluña, junto a Manresa',
             'Con 1.450 metros de trazado, es el circuito de karts más largo de Catalunya y uno de los más largos de España y Europa. Asfaltado renovado en 2020, ofrece curvas, peraltes, cambios de rasante y largas rectas para ir a máxima velocidad. Dispone de karts hasta 400cc, escuela de pilotos Kids to Win para niños desde 6 anos, bar, terraza al aire libre y garajes. A 35 minutos de Barcelona.',
             1450, 100, 'Outdoor', 'Avanzado', 12, 22.00, '#FF00A8', '💎', 'https://www.kartingsallent.com'),
            ('Karting Coma-Ruga', 'Coma-ruga', 'Ctra. Nal. 340, Km. 1188, 43880 Coma-ruga, Tarragona',
             'El circuito donde empezaron Alex y Marc Marquez',
             'Karting outdoor de 850 metros con 40.000 m2 de instalaciones y 250 plazas de parking. A 20 minutos de Tarragona y 45 de Barcelona, a 300 metros de la playa de Coma-ruga. Circuito adultos técnico con Super-kart SODI RT-10 400cc, únicos en la provincia. Mas de 30 años de historia con bar, terraza y zona de barbacoa.',
             850, 80, 'Outdoor', 'Intermedio', 12, 20.00, '#FF4D00', '', 'https://kartingcomaruga.com'),
            ('Karting Vendrell', 'El Vendrell', 'Crta. N-340, Km. 1189, 43700 El Vendrell, Tarragona',
             'Uno de los mejores circuitos de karts de Europa',
             'Circuito outdoor de 1.275 metros con 8 curvas a derechas y 6 a izquierdas. Trazado técnico de nivel internacional donde han rodado Fernando Alonso, Pedro de la Rosa y Carlos Sainz. Karts GTMax Rotax 125cc de 30 cv que alcanzan 95 km/h. También paintball, laser tag y barbacoa. A 35 minutos de Barcelona.',
             1275, 95, 'Outdoor', 'Avanzado', 14, 25.00, '#FF4D00', '', 'https://kartingvendrell.com'),
            ('Karting Calafat', "L'Ametlla de Mar", 'Urb. San Jorge S Autop, 43860 Calafat, Tarragona',
             'Circuito técnico outdoor a 300 metros de la playa en el mítico Circuit de Calafat',
             'Circuito outdoor de 700 metros con 6 curvas a derechas y 3 a izquierdas, dos chicanes y 7-10 metros de anchura. Inaugurado en 2022 en las instalaciones del legendario Circuit de Calafat. Cronometraje profesional, podium y medallas. Parking propio, terraza con bebidas y snacks, zona de barbacoa, briefing previo y zona ludica con piscina y parque infantil. A 48 km de Tarragona y muy cerca de la playa.',
             700, 80, 'Outdoor', 'Intermedio', 12, 18.00, '#FF4D00', '', 'https://karting.circuitcalafat.com'),
            ('Circuit d\'Osona Karting', 'Vic', 'Carrer Cabreres, 2, 08500 Vic',
             'Circuito de referencia en el corazon de Cataluña',
             'Pista outdoor de 940 metros de longitud y 8 metros de ancho ubicada en Vic, a 45 minutos de Barcelona. Trazado muy versátil con innumerables variantes que lo hacen único. Sede habitual de competiciones oficiales y campeónatos regionales. Dispone de escuela de karts y talleres de carreras. Anualmente acoge las legendarias 24 Horas de Osona. Ideal para pilotos que buscan mejorar su nivel.',
             940, 80, 'Outdoor', 'Avanzado', 10, 20.00, '#FF8C00', '🏁', 'https://www.kartingosona.com'),
        ]
        c.executemany('''INSERT INTO circuits (name,location,address,description,long_description,length_m,max_speed_kmh,track_type,difficulty,max_per_session,price_per_session,color,emoji,website)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', circuits)
        conn.commit()

    # ── SEED TEST USERS ──
    pwd = hashlib.sha256('123456'.encode()).hexdigest()

    # Pilots
    for u, n, ap in [('piloto1','Carlos','García'),('piloto2','Laura','Martínez')]:
        existing = c.execute('SELECT id FROM users WHERE username=?',(u,)).fetchone()
        if not existing:
            c.execute('''INSERT INTO users (username,email,password_hash,full_name,apellido,is_admin,karting_level)
                VALUES (?,?,?,?,?,0,'Novato')''',
                (u, f'{u}@kartnation.test', pwd, n, ap))

    # Admins
    for u, n, ap in [('admin1','Miguel','Sánchez'),('admin2','Ana','López')]:
        existing = c.execute('SELECT id FROM users WHERE username=?',(u,)).fetchone()
        if not existing:
            c.execute('''INSERT INTO users (username,email,password_hash,full_name,apellido,is_admin,karting_level)
                VALUES (?,?,?,?,?,1,'Experto')''',
                (u, f'{u}@kartnation.test', pwd, n, ap))

    # Karting accounts — test
    for u, name, city in [('karting1','Karting Test Uno','Barcelona'),('karting2','Karting Test Dos','Tarragona')]:
        existing = c.execute('SELECT id FROM circuit_accounts WHERE username=?',(u,)).fetchone()
        if not existing:
            c.execute('''INSERT INTO circuit_accounts (username,circuit_name,city,password_hash)
                VALUES (?,?,?,?)''', (u, name, city, pwd))

    # Karting accounts — 9 circuitos reales
    real_circuits = [
        ('genekarting',       'Gené Karting',                  'Viladecans'),
        ('indoorbarcelona',   'Indoor Karting Barcelona',       'Sant Feliu de Llobregat'),
        ('kartingcardedeu',   'Karting Cardedeu',               'Cardedeu'),
        ('kartingcastelloli', 'Karting Castellolí - ParcMotor', 'Castellolí'),
        ('kartingsallent',    'Karting Sallent',                'Sallent'),
        ('kartingcomaruga',   'Karting Coma-Ruga',              'Coma-ruga'),
        ('kartingvendrell',   'Karting Vendrell',               'El Vendrell'),
        ('kartingcalafat',    'Karting Calafat',                "L'Ametlla de Mar"),
        ('kartingosona',      "Circuit d'Osona Karting",        'Vic'),
    ]
    for u, name, city in real_circuits:
        existing = c.execute('SELECT id FROM circuit_accounts WHERE username=?',(u,)).fetchone()
        if not existing:
            c.execute('''INSERT INTO circuit_accounts (username,circuit_name,city,password_hash)
                VALUES (?,?,?,?)''', (u, name, city, pwd))

    # Fill circuit_info for real circuits
    circuit_details = {
        'genekarting': {
            'display_name': 'Gené Karting',
            'address': 'Avda. del Siglo XXI, nº6, CC Vilamarina, 08840 Viladecans',
            'city': 'Viladecans',
            'length_m': 500,
            'max_per_session': 10,
            'phone': '+34 937 836 425',
            'website': 'https://www.barcelonagenekarting.com',
            'description': 'Karting indoor diseñado por Marc Gené. 3 circuitos: adulto, junior y Veodrive. A 16 km de Barcelona en el CC Vilamarina.',
        },
        'indoorbarcelona': {
            'display_name': 'Indoor Karting Barcelona',
            'address': 'Pol. Ind. El Pla, Carrer de Laureà Miró, 434, 08980 Sant Feliu de Llobregat',
            'city': 'Sant Feliu de Llobregat',
            'length_m': 500,
            'max_per_session': 15,
            'phone': '+34 936 857 500',
            'website': 'https://www.indoorkartingbarcelona.com',
            'description': 'El primer circuito indoor de España. 5.000 m² de instalaciones con bolera y Laser Tag. A 11 km de Barcelona.',
        },
        'kartingcardedeu': {
            'display_name': 'Karting Cardedeu',
            'address': 'Ctra. Granollers a Sant Celoni (C-251), Km 5.300, 08440 Cardedeu',
            'city': 'Cardedeu',
            'length_m': 750,
            'max_per_session': 12,
            'phone': '+34 938 712 453',
            'website': 'https://www.kartingcardedeu.com',
            'description': 'Circuito outdoor técnico de 750m a 35 km de Barcelona. Iluminación nocturna y 5 tipos de karts.',
        },
        'kartingcastelloli': {
            'display_name': 'Karting Castellolí - ParcMotor',
            'address': 'Crta. Nacional A-2, Km 560, 08719 Castellolí, Barcelona',
            'city': 'Castellolí',
            'length_m': 1340,
            'max_per_session': 12,
            'phone': '+34 616 500 600',
            'website': 'https://www.kartingparcmotor.com',
            'description': 'Circuito de 1.340m diseñado por Dani Pedrosa. Réplica de F1. El más espectacular de Cataluña. A 25 min de Barcelona.',
        },
        'kartingsallent': {
            'display_name': 'Karting Sallent',
            'address': 'Ctra. C-16, km 58,5, 08650 Sallent, Barcelona',
            'city': 'Sallent',
            'length_m': 1450,
            'max_per_session': 12,
            'phone': '+34 629 308 407',
            'website': 'https://www.kartingsallent.com',
            'description': 'El circuito de karts más largo de Cataluña. 1.450m reaslfaltados en 2020. Bar y terraza. A 35 min de Barcelona.',
        },
        'kartingcomaruga': {
            'display_name': 'Karting Coma-Ruga',
            'address': 'Ctra. Nal. 340, Km. 1188, 43880 Coma-ruga, Tarragona',
            'city': 'Coma-ruga',
            'length_m': 850,
            'max_per_session': 12,
            'phone': '+34 678 320 656',
            'website': 'https://kartingcomaruga.com',
            'description': 'El circuito donde empezaron Alex y Marc Márquez. 30 años de historia. Super-kart 400cc únicos en la provincia.',
        },
        'kartingvendrell': {
            'display_name': 'Karting Vendrell',
            'address': 'Ctra. N-340, Km. 1189, 43700 El Vendrell, Tarragona',
            'city': 'El Vendrell',
            'length_m': 1275,
            'max_per_session': 14,
            'phone': '+34 977 663 776',
            'website': 'https://kartingvendrell.com',
            'description': 'Circuito de 1.275m de nivel internacional. Karts GTMax Rotax 125cc de 30cv. Han rodado Alonso, De la Rosa y Sainz.',
        },
        'kartingcalafat': {
            'display_name': 'Karting Calafat',
            'address': "Urb. San Jorge, Autovía AP-7, 43860 L'Ametlla de Mar, Tarragona",
            'city': "L'Ametlla de Mar",
            'length_m': 700,
            'max_per_session': 12,
            'phone': '',
            'website': 'https://karting.circuitcalafat.com',
            'description': 'Circuito outdoor de 700m inaugurado en 2022 en el mítico Circuit de Calafat. A 300m de la playa.',
        },
        'kartingosona': {
            'display_name': "Circuit d'Osona Karting",
            'address': "C/ Cabrerès, 2, Pol. Ind. Malloles, 08500 Vic",
            'city': 'Vic',
            'length_m': 940,
            'max_per_session': 10,
            'phone': '+34 938 866 036',
            'website': 'https://www.circuitosona.com',
            'description': 'Circuito de referencia en Osona. 940m y múltiples variantes. Sede de las legendarias 24 Horas. A 45 min de Barcelona.',
        },
    }
    for username, details in circuit_details.items():
        acc = c.execute('SELECT id FROM circuit_accounts WHERE username=?',(username,)).fetchone()
        if acc:
            acc_id = acc['id']
            existing_info = c.execute('SELECT id FROM circuit_info WHERE account_id=?',(acc_id,)).fetchone()
            if not existing_info:
                c.execute('''INSERT INTO circuit_info
                    (account_id,display_name,address,city,length_m,max_per_session,phone,website,description)
                    VALUES (?,?,?,?,?,?,?,?,?)''',
                    (acc_id, details['display_name'], details['address'], details['city'],
                     details['length_m'], details['max_per_session'], details['phone'],
                     details['website'], details['description']))

    # ── SEED SCHEDULES for real circuits ──
    # Format: {username: {weekday(0=mon): (open, close) or None if closed}}
    circuit_schedules = {
        'genekarting': {
            0:('17:00','22:00'), 1:('17:00','22:00'), 2:('17:00','22:00'),
            3:('11:00','22:00'), 4:('11:00','23:59'), 5:('11:00','23:59'), 6:('11:00','22:00'),
        },
        'indoorbarcelona': {
            0:('16:00','23:00'), 1:('16:00','23:00'), 2:('16:00','23:00'), 3:('16:00','23:00'),
            4:('16:00','23:59'), 5:('10:00','23:59'), 6:('10:00','23:00'),
        },
        'kartingcardedeu': {
            0:('11:00','20:00'), 1:('11:00','20:00'), 2:('11:00','20:30'), 3:('11:00','20:30'),
            4:('11:00','20:30'), 5:('10:00','21:00'), 6:('10:00','21:00'),
        },
        'kartingcastelloli': {
            0:('10:00','18:30'), 1:('10:00','18:30'), 2:('10:00','18:30'), 3:('10:00','18:30'),
            4:('10:00','18:30'), 5:('10:00','18:30'), 6:('10:00','18:30'),
        },
        'kartingsallent': {
            0: None, 1: None,
            2:('10:00','20:30'), 3:('10:00','20:30'), 4:('10:00','20:30'),
            5:('10:00','20:30'), 6:('10:00','20:30'),
        },
        'kartingcomaruga': {
            0:('10:00','22:00'), 1:('10:00','22:00'), 2:('10:00','22:00'), 3:('10:00','22:00'),
            4:('10:00','22:00'), 5:('10:00','22:00'), 6:('10:00','22:00'),
        },
        'kartingvendrell': {
            0:('10:00','20:00'), 1:('10:00','20:00'), 2:('10:00','20:00'), 3:('10:00','20:00'),
            4:('10:00','20:00'), 5:('10:00','20:00'), 6:('10:00','20:00'),
        },
        'kartingcalafat': {
            0: None, 1: None, 2: None, 3: None, 4: None,
            5:('10:00','20:00'), 6:('10:00','20:00'),
        },
        'kartingosona': {
            0:('10:00','20:00'), 1:('10:00','20:00'), 2:('10:00','20:00'), 3:('10:00','21:00'),
            4:('10:00','20:00'), 5:('10:00','21:00'), 6:('10:00','21:00'),
        },
    }
    for username, sched in circuit_schedules.items():
        acc = c.execute('SELECT id FROM circuit_accounts WHERE username=?',(username,)).fetchone()
        if acc:
            acc_id = acc['id']
            for wd, hours in sched.items():
                existing = c.execute('SELECT id FROM circuit_schedule WHERE account_id=? AND weekday=?',(acc_id,wd)).fetchone()
                if not existing:
                    if hours is None:
                        c.execute('INSERT INTO circuit_schedule (account_id,weekday,open_time,close_time,is_closed) VALUES (?,?,?,?,1)',
                            (acc_id, wd, '', ''))
                    else:
                        c.execute('INSERT INTO circuit_schedule (account_id,weekday,open_time,close_time,is_closed) VALUES (?,?,?,?,0)',
                            (acc_id, wd, hours[0], hours[1]))

    # Link pitlane accounts to main circuits (run after all seeds)
    username_to_circuit = {
        'genekarting':       'Gene Karting',
        'indoorbarcelona':   'Indoor Karting Barcelona',
        'kartingcardedeu':   'Karting Cardedeu',
        'kartingcastelloli': 'Karting Castelloli - ParcMotor',
        'kartingsallent':    'Karting Sallent',
        'kartingcomaruga':   'Karting Coma-Ruga',
        'kartingvendrell':   'Karting Vendrell',
        'kartingcalafat':    'Karting Calafat',
        'kartingosona':      "Circuit d'Osona Karting",
    }
    for username, circuit_name in username_to_circuit.items():
        acc = c.execute('SELECT id FROM circuit_accounts WHERE username=?',(username,)).fetchone()
        circuit = c.execute('SELECT id FROM circuits WHERE name=?',(circuit_name,)).fetchone()
        if acc and circuit:
            c.execute('UPDATE circuit_accounts SET linked_circuit_id=? WHERE id=?',
                (circuit['id'], acc['id']))

    conn.commit()
    conn.close()

def hash_password(p): return hashlib.sha256(p.encode()).hexdigest()

def generate_time_slots(circuit_name=None, weekday=None):
    """Generate 15-min slots for a circuit on a given weekday.
    If no circuit_name, returns full 08:00-18:00 range (fallback)."""
    if circuit_name and weekday is not None and circuit_name in CIRCUIT_HOURS:
        day_hours = CIRCUIT_HOURS[circuit_name].get(weekday, [])
        slots = []
        for (oh, om, ch, cm) in day_hours:
            cur = datetime.strptime(f'{oh:02d}:{om:02d}', '%H:%M')
            end = datetime.strptime(f'{ch:02d}:{cm:02d}', '%H:%M')
            while cur <= end:
                slot = cur.strftime('%H:%M')
                if slot not in slots:
                    slots.append(slot)
                cur += timedelta(minutes=15)
        return slots
    # fallback
    slots, cur = [], datetime.strptime('08:00','%H:%M')
    end = datetime.strptime('23:45','%H:%M')
    while cur <= end:
        slots.append(cur.strftime('%H:%M'))
        cur += timedelta(minutes=15)
    return slots

def login_required(f):
    @wraps(f)
    def d(*a,**kw):
        if 'user_id' not in session:
            flash('Debes iniciar sesión para continuar.','warning')
            return redirect(url_for('login'))
        return f(*a,**kw)
    return d

def admin_required(f):
    @wraps(f)
    def d(*a,**kw):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        conn = get_db()
        u = conn.execute('SELECT is_admin FROM users WHERE id=?',(session['user_id'],)).fetchone()
        conn.close()
        if not u or not u['is_admin']:
            flash('Acceso restringido a administradores.','error')
            return redirect(url_for('index'))
        return f(*a,**kw)
    return d

def get_kart_group(kart_name):
    """Returns 'B' for biplaza/junior/infantil karts, 'A' for adulto/general karts.
    Used for kart_mix_policy='separate' to decide tanda compatibility."""
    name_lower = (kart_name or '').lower()
    if any(k in name_lower for k in ['biplaza', 'junior', 'infantil']):
        return 'B'
    return 'A'

def get_karting_level_info(level):
    levels = {
        'Novato':     {'color':'#7CFF00','order':1,'icon':'🟢'},
        'Intermedio': {'color':'#FFD700','order':2,'icon':'🟡'},
        'Avanzado':   {'color':'#FF8C00','order':3,'icon':'🟠'},
        'Experto':    {'color':'#FF2D55','order':4,'icon':'🔴'},
    }
    return levels.get(level, levels['Novato'])

# ── OPENING HOURS (hora España = UTC+1 invierno / UTC+2 verano) ──
# Formato: {dia_semana(0=lun..6=dom): [(open_h, open_m, close_h, close_m), ...]}
CIRCUIT_HOURS = {
    'Gene Karting': {
        0: [(17,0,22,0)],  # lunes
        1: [(17,0,22,0)],  # martes
        2: [(17,0,22,0)],  # miercoles
        3: [(11,0,22,0)],  # jueves
        4: [(11,0,23,59)], # viernes
        5: [(11,0,23,59)], # sabado
        6: [(11,0,22,0)],  # domingo
    },
    'Indoor Karting Barcelona': {
        0: [(16,0,23,0)],
        1: [(16,0,23,0)],
        2: [(16,0,23,0)],
        3: [(16,0,23,0)],
        4: [(16,0,23,59)],
        5: [(10,0,23,59)],
        6: [(10,0,23,0)],
    },
    'Karting Cardedeu': {
        0: [(11,0,14,0),(15,0,20,0)],
        1: [(11,0,14,0),(15,0,20,0)],
        2: [(11,0,14,0),(15,0,20,30)],
        3: [(11,0,14,0),(15,0,20,30)],
        4: [(11,0,14,0),(15,0,20,30)],
        5: [(10,0,21,0)],
        6: [(10,0,21,0)],
    },
    'Karting Castelloli - ParcMotor': {
        0: [(10,0,14,0),(15,0,18,30)],
        1: [(10,0,14,0),(15,0,18,30)],
        2: [(10,0,14,0),(15,0,18,30)],
        3: [(10,0,14,0),(15,0,18,30)],
        4: [(10,0,14,0),(15,0,18,30)],
        5: [(10,0,18,30)],
        6: [(10,0,18,30)],
    },
    'Karting Sallent': {
        0: [],  # lunes cerrado
        1: [],  # martes cerrado
        2: [(10,0,20,30)],
        3: [(10,0,20,30)],
        4: [(10,0,20,30)],
        5: [(10,0,20,30)],
        6: [(10,0,20,30)],
    },
    'Karting Calafat': {
        0: [],  # lunes cerrado (temporada baja)
        1: [],
        2: [],
        3: [],
        4: [],
        5: [(10,0,14,0),(16,0,20,0)],  # sabado
        6: [(10,0,14,0),(16,0,20,0)],  # domingo
    },
        'Karting Coma-Ruga': {
        0: [(10,0,22,0)],
        1: [(10,0,22,0)],
        2: [(10,0,22,0)],
        3: [(10,0,22,0)],
        4: [(10,0,22,0)],
        5: [(10,0,22,0)],
        6: [(10,0,22,0)],
    },
    'Karting Vendrell': {
        0: [(10,0,14,0),(16,0,20,0)],
        1: [(10,0,14,0),(16,0,20,0)],
        2: [(10,0,14,0),(16,0,20,0)],
        3: [(10,0,14,0),(16,0,20,0)],
        4: [(10,0,14,0),(16,0,20,0)],
        5: [(10,0,20,0)],
        6: [(10,0,20,0)],
    },
    "Circuit d'Osona Karting": {
        0: [(10,0,14,0),(15,0,20,0)],
        1: [(10,0,14,0),(15,0,20,0)],
        2: [(10,0,14,0),(15,0,20,0)],
        3: [(10,0,21,0)],
        4: [(10,0,14,0),(15,0,20,0)],
        5: [(10,0,21,0)],
        6: [(10,0,21,0)],
    },
}

def is_circuit_open(circuit_name):
    from datetime import timezone, timedelta as td
    spain_tz = timezone(td(hours=1))
    now = datetime.now(spain_tz)
    weekday = now.weekday()
    hours = CIRCUIT_HOURS.get(circuit_name, {}).get(weekday, [])
    for (oh, om, ch, cm) in hours:
        open_dt = now.replace(hour=oh, minute=om, second=0, microsecond=0)
        close_dt = now.replace(hour=ch, minute=cm, second=0, microsecond=0)
        if open_dt <= now <= close_dt:
            return True, oh, om, ch, cm
    # Find next opening
    return False, None, None, None, None

def send_reset_email(to_email, to_name, reset_link):
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = 'KARTNATION - Restablecer contrasena'
        msg['From'] = f"{EMAIL_CONFIG['EMAIL_FROM_NAME']} <{EMAIL_CONFIG['EMAIL_USER']}>"
        msg['To'] = to_email
        html = f"""<html><body style="background:#0A0A0B;color:#F0EEE8;font-family:Arial,sans-serif;padding:2rem;">
        <div style="max-width:480px;margin:0 auto;background:#111114;border:1px solid rgba(255,255,255,0.1);border-radius:8px;overflow:hidden;">
        <div style="height:4px;background:linear-gradient(90deg,#FF4D00,#FFD700);"></div>
        <div style="padding:2rem;">
        <h2 style="color:#FF4D00;">KARTNATION - Restablecer contrasena</h2>
        <p style="color:#7A7A85;">Hola <strong style="color:#F0EEE8;">{to_name}</strong>,</p>
        <p style="color:#7A7A85;">Haz clic para crear una nueva contrasena:</p>
        <a href="{reset_link}" style="display:inline-block;background:#FF4D00;color:#fff;text-decoration:none;padding:0.75rem 2rem;border-radius:4px;font-weight:700;">Restablecer contrasena</a>
        <p style="color:#4A4A55;font-size:0.82rem;margin-top:1rem;">Este enlace expira en 1 hora.</p>
        </div></div></body></html>"""
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP(EMAIL_CONFIG['SMTP_SERVER'], EMAIL_CONFIG['SMTP_PORT']) as server:
            server.starttls()
            server.login(EMAIL_CONFIG['EMAIL_USER'], EMAIL_CONFIG['EMAIL_PASS'])
            server.sendmail(EMAIL_CONFIG['EMAIL_USER'], to_email, msg.as_string())
        return True
    except Exception as e:
        print(f'[EMAIL ERROR] {e}')
        return False

@app.route('/')
def index():
    user = None
    if 'user_id' in session:
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
        conn.close()
    return render_template('index.html', user=user)

@app.route('/circuitos')
def circuitos():
    conn = get_db()
    circuits = conn.execute('SELECT * FROM circuits').fetchall()
    today = date.today().isoformat()
    popular_slots = []
    for c in circuits:
        count = conn.execute('SELECT COUNT(*) as cnt FROM bookings WHERE circuit_id=? AND booking_date>=?',(c['id'],today)).fetchone()['cnt']
        popular_slots.append({'circuit':c,'bookings':count})

    time_slots = generate_time_slots()
    lengths = [c['length_m'] for c in circuits]
    min_length = min(lengths) if lengths else 0
    max_length = max(lengths) if lengths else 2000

    conn.close()
    user = None
    if 'user_id' in session:
        conn2 = get_db()
        user = conn2.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
        conn2.close()
    return render_template('circuitos.html', circuits=circuits, popular_slots=popular_slots,
                           user=user, time_slots=time_slots,
                           min_length=min_length, max_length=max_length, today=today)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        full_name = request.form['full_name'].strip()
        apellido = request.form.get('apellido','').strip()
        fecha_nacimiento = request.form.get('fecha_nacimiento','').strip()
        teléfono = request.form.get('teléfono','').strip()
        is_admin = 1 if request.form.get('is_admin') == '1' else 0
        admin_code = request.form.get('admin_code','').strip()

        if not apellido:
            flash('El apellido es obligatorio.','error')
            return render_template('register.html')
        if not fecha_nacimiento:
            flash('La fecha de nacimiento es obligatoria.','error')
            return render_template('register.html')
        if not teléfono:
            flash('El teléfono es obligatorio.','error')
            return render_template('register.html')
        if is_admin and admin_code != 'KARTNATION_ADMIN_2024':
            flash('Codigo de administrador incorrecto.','error')
            return render_template('register.html')
        if len(password) < 6:
            flash('La contrasena debe tener al menos 6 caracteres.','error')
            return render_template('register.html')
        avatar_initial = full_name[0].upper() if full_name else username[0].upper()
        conn = get_db()
        try:
            conn.execute('''INSERT INTO users
                (username,email,password_hash,full_name,apellido,fecha_nacimiento,teléfono,avatar_initial,is_admin)
                VALUES (?,?,?,?,?,?,?,?,?)''',
                (username,email,hash_password(password),full_name,apellido,fecha_nacimiento,teléfono,avatar_initial,is_admin))
            conn.commit()
            flash('Cuenta creada con exito! Ya puedes iniciar sesión.','success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Ese nombre de usuario o email ya esta en uso.','error')
        finally:
            conn.close()
    from datetime import date as _date
    max_date = _date.today().isoformat()
    today = _date.today().isoformat()
    return render_template('register.html', max_date=max_date, today=today)

@app.route('/admin-login', methods=['GET','POST'])
def admin_login():
    if session.get('user_id') and not session.get('is_admin'):
        flash('Debes cerrar sesión como piloto antes de acceder al panel de administración.', 'error')
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        conn = get_db()
        user = conn.execute(
            'SELECT * FROM users WHERE username=? AND password_hash=? AND is_admin=1',
            (username, hash_password(password))
        ).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = True
            flash(f'Bienvenido al panel, {user["full_name"].split()[0]}.', 'success')
            return redirect(url_for('admin_panel'))
        else:
            flash('Credenciales incorrectas o cuenta sin permisos de administrador.', 'error')
    return render_template('admin_login.html')

@app.route('/admin-register', methods=['GET','POST'])
def admin_register():
    if request.method == 'POST':
        full_name = request.form['full_name'].strip()
        username = request.form['username'].strip()
        email = request.form['email'].strip()
        password = request.form['password']
        admin_code = request.form['admin_code'].strip()

        if admin_code != 'KARTNATION_ADMIN_2024':
            flash('Codigo de administrador incorrecto.', 'error')
            return render_template('admin_register.html')
        if len(password) < 6:
            flash('La contrasena debe tener al menos 6 caracteres.', 'error')
            return render_template('admin_register.html')

        avatar_initial = full_name[0].upper() if full_name else username[0].upper()
        conn = get_db()
        try:
            conn.execute(
                'INSERT INTO users (username,email,password_hash,full_name,avatar_initial,is_admin) VALUES (?,?,?,?,?,1)',
                (username, email, hash_password(password), full_name, avatar_initial)
            )
            conn.commit()
            flash('Cuenta de administrador creada. Ya puedes iniciar sesión.', 'success')
            return redirect(url_for('admin_login'))
        except sqlite3.IntegrityError:
            flash('Ese nombre de usuario o email ya esta en uso.', 'error')
        finally:
            conn.close()
    return render_template('admin_register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username=? AND password_hash=?',(username,hash_password(password))).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            flash(f'Bienvenido, {user["full_name"].split()[0]}!','success')
            return redirect(url_for('admin_panel') if user['is_admin'] else url_for('index'))
        else:
            flash('Usuario o contrasena incorrectos.','error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesion cerrada.','info')
    return redirect(url_for('index'))

@app.route('/profile')
@login_required
def profile():
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
    bookings = conn.execute('''SELECT b.*, c.name as circuit_name, c.location, c.color, c.emoji, c.price_per_session,
        kt.name as kart_name
        FROM bookings b JOIN circuits c ON b.circuit_id=c.id
        LEFT JOIN kart_types kt ON b.kart_type_id=kt.id
        WHERE b.user_id=? ORDER BY b.booking_date DESC, b.time_slot DESC''',(session['user_id'],)).fetchall()
    conn.close()
    level_info = get_karting_level_info(user['karting_level'])
    today = date.today().isoformat()
    return render_template('profile.html', user=user, bookings=bookings, level_info=level_info, today=today)

@app.route('/profile/edit', methods=['GET','POST'])
@login_required
def profile_edit():
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
    if request.method == 'POST':
        full_name = request.form.get('full_name','').strip()
        apellido = request.form.get('apellido','').strip()
        fecha_nacimiento = request.form.get('fecha_nacimiento','').strip()
        teléfono = request.form.get('teléfono','').strip()
        dni = request.form.get('dni','').strip().upper()
        bio = request.form.get('bio','').strip()
        new_password = request.form.get('new_password','').strip()
        confirm_password = request.form.get('confirm_password','').strip()

        if not full_name or not apellido or not teléfono:
            flash('Nombre, apellido y teléfono son obligatorios.','error')
            conn.close()
            return render_template('profile_edit.html', user=user, now_date=date.today().isoformat())

        updates = {
            'full_name': full_name,
            'apellido': apellido,
            'fecha_nacimiento': fecha_nacimiento,
            'teléfono': teléfono,
            'dni': dni,
            'bio': bio,
            'avatar_initial': full_name[0].upper() if full_name else user['avatar_initial'],
        }

        if new_password:
            if len(new_password) < 6:
                flash('La nueva contrasena debe tener al menos 6 caracteres.','error')
                conn.close()
                return render_template('profile_edit.html', user=user, now_date=date.today().isoformat())
            if new_password != confirm_password:
                flash('Las contrasenas no coinciden.','error')
                conn.close()
                return render_template('profile_edit.html', user=user, now_date=date.today().isoformat())
            updates['password_hash'] = hash_password(new_password)

        set_clause = ', '.join(f'{k}=?' for k in updates)
        conn.execute(f'UPDATE users SET {set_clause} WHERE id=?',
                     list(updates.values()) + [session['user_id']])
        conn.commit()
        conn.close()
        flash('Datos actualizados correctamente.','success')
        return redirect(url_for('profile'))

    conn.close()
    return render_template('profile_edit.html', user=user, now_date=date.today().isoformat())

@app.route('/circuit/<int:circuit_id>')
def circuit_detail(circuit_id):
    conn = get_db()
    circuit = conn.execute('SELECT * FROM circuits WHERE id=?',(circuit_id,)).fetchone()
    if not circuit:
        flash('Circuito no encontrado.','error')
        return redirect(url_for('index'))
    # Default date: next day the circuit is open
    default_date = next_open_date(circuit['name'])
    selected_date = request.args.get('date', default_date)
    # Get weekday for selected date to generate correct slots
    try:
        sel_weekday = datetime.strptime(selected_date, '%Y-%m-%d').weekday()
    except:
        sel_weekday = datetime.today().weekday()
    time_slots = generate_time_slots(circuit['name'], sel_weekday)
    # Fallback if closed that day
    if not time_slots:
        time_slots = generate_time_slots()
    # Get linked pitlane account for this circuit
    pitlane_acc = conn.execute('SELECT id FROM circuit_accounts WHERE linked_circuit_id=?',(circuit_id,)).fetchone()
    pitlane_acc_id = pitlane_acc['id'] if pitlane_acc else None

    # All kart types come from unified kart_types table, keyed by circuit_id
    kart_types = [dict(k) for k in conn.execute('SELECT * FROM kart_types WHERE circuit_id=?',(circuit_id,)).fetchall()]

    # Get pitlane price if configured
    pitlane_info = conn.execute('SELECT price_per_session FROM circuit_info WHERE account_id=?',(pitlane_acc_id,)).fetchone() if pitlane_acc_id else None
    pitlane_price = pitlane_info['price_per_session'] if pitlane_info and pitlane_info['price_per_session'] else None

    slot_data = {}
    for slot in time_slots:
        bookings = conn.execute('''SELECT u.username, u.full_name, u.karting_level, u.avatar_initial, u.races_completed,
            kt.name as kart_name
            FROM bookings b JOIN users u ON b.user_id=u.id
            LEFT JOIN kart_types kt ON b.kart_type_id=kt.id
            WHERE b.circuit_id=? AND b.booking_date=? AND b.time_slot=?''',(circuit_id,selected_date,slot)).fetchall()

        # Admin manual bookings for this slot
        manual = conn.execute('''SELECT mb.*, kt.name as kart_name
            FROM manual_bookings mb LEFT JOIN kart_types kt ON mb.kart_type_id=kt.id
            WHERE mb.circuit_id=? AND mb.booking_date=? AND mb.time_slot=?''',(circuit_id,selected_date,slot)).fetchall()
        manual_count = sum(m['num_pilots'] for m in manual)

        # PitLane circuit manual bookings
        pitlane_count = 0
        if pitlane_acc_id:
            pl_rows = conn.execute(
                'SELECT num_pilots FROM circuit_manual_bookings WHERE account_id=? AND booking_date=? AND time_slot=?',
                (pitlane_acc_id, selected_date, slot)
            ).fetchall()
            pitlane_count = sum(r['num_pilots'] for r in pl_rows)

        user_booked = False
        if 'user_id' in session:
            user_booked = any(b['username']==session.get('username') for b in bookings)

        total_count = len(bookings) + manual_count + pitlane_count

        # Get the locked kart type for this slot (first booking defines it)
        locked = conn.execute(
            '''SELECT kt.id, kt.name, kt.engine_cc FROM bookings b
               JOIN kart_types kt ON b.kart_type_id=kt.id
               WHERE b.circuit_id=? AND b.booking_date=? AND b.time_slot=?
               LIMIT 1''',
            (circuit_id, selected_date, slot)
        ).fetchone()

        # Check manual bookings for locked kart if no online booking
        if not locked:
            locked_manual = conn.execute(
                '''SELECT kt.id, kt.name FROM manual_bookings mb
                   JOIN kart_types kt ON mb.kart_type_id=kt.id
                   WHERE mb.circuit_id=? AND mb.booking_date=? AND mb.time_slot=?
                   LIMIT 1''',
                (circuit_id, selected_date, slot)
            ).fetchone()
            if locked_manual:
                locked = locked_manual

        kart_mix_policy = circuit['kart_mix_policy'] if circuit['kart_mix_policy'] else 'all'
        locked_group = get_kart_group(locked['name']) if locked else None

        slot_data[slot] = {
            'bookings': [dict(b) for b in bookings],
            'manual': [dict(m) for m in manual],
            'count': total_count,
            'available': max(0, circuit['max_per_session'] - total_count),
            'user_booked': user_booked,
            'locked_kart_id': locked['id'] if locked else None,
            'locked_kart_name': locked['name'] if locked else None,
            'locked_kart_group': locked_group,
            'kart_mix_policy': kart_mix_policy,
        }

    user = None
    if 'user_id' in session:
        user = conn.execute('SELECT * FROM users WHERE id=?',(session['user_id'],)).fetchone()
    conn.close()
    return render_template('circuit.html', circuit=circuit, slot_data=slot_data,
                           time_slots=time_slots, selected_date=selected_date, user=user,
                           kart_types=kart_types, level_fn=get_karting_level_info,
                           now=datetime.now().strftime('%H:%M'), today=date.today().isoformat(),
                           default_date=default_date, pitlane_price=pitlane_price)

@app.route('/api/complete-profile', methods=['POST'])
@login_required
def api_complete_profile():
    dni = request.form.get('dni', '').strip().upper()
    fecha_nacimiento = request.form.get('fecha_nacimiento', '').strip()
    if not dni and not fecha_nacimiento:
        return jsonify({'ok': False, 'error': 'No se proporcionaron datos.'})
    updates = []
    values = []
    if dni:
        updates.append('dni=?')
        values.append(dni)
    if fecha_nacimiento:
        updates.append('fecha_nacimiento=?')
        values.append(fecha_nacimiento)
    values.append(session['user_id'])
    conn = get_db()
    conn.execute(f'UPDATE users SET {", ".join(updates)} WHERE id=?', values)
    conn.commit()
    conn.close()
    return jsonify({'ok': True})

def _check_profile_complete():
    conn = get_db()
    user = conn.execute('SELECT dni, fecha_nacimiento FROM users WHERE id=?', (session['user_id'],)).fetchone()
    conn.close()
    missing = []
    if not user['dni']:
        missing.append('DNI')
    if not user['fecha_nacimiento']:
        missing.append('fecha de nacimiento')
    return missing

@app.route('/book', methods=['POST'])
@login_required
def book_slot():
    missing = _check_profile_complete()
    if missing:
        flash(f'Debes completar tu perfil antes de reservar. Faltan: {", ".join(missing)}.', 'error')
        return redirect(url_for('profile_edit'))

    circuit_id = request.form['circuit_id']
    booking_date = request.form['booking_date']
    time_slot = request.form['time_slot']
    kart_type_id = request.form.get('kart_type_id') or None

    # Block past date OR past time slot on today
    now = datetime.now()
    slot_dt = datetime.strptime(f'{booking_date} {time_slot}', '%Y-%m-%d %H:%M')
    if slot_dt <= now:
        flash('No puedes reservar en una fecha u hora que ya ha pasado.', 'error')
        return redirect(url_for('circuit_detail', circuit_id=circuit_id, date=booking_date))

    conn = get_db()
    circuit = conn.execute('SELECT * FROM circuits WHERE id=?',(circuit_id,)).fetchone()

    # Count online + manual bookings
    online_count = conn.execute('SELECT COUNT(*) as cnt FROM bookings WHERE circuit_id=? AND booking_date=? AND time_slot=?',
        (circuit_id,booking_date,time_slot)).fetchone()['cnt']
    manual_rows = conn.execute('SELECT num_pilots FROM manual_bookings WHERE circuit_id=? AND booking_date=? AND time_slot=?',
        (circuit_id,booking_date,time_slot)).fetchall()
    manual_count = sum(r['num_pilots'] for r in manual_rows)
    # PitLane circuit bookings
    pitlane_acc2 = conn.execute('SELECT id FROM circuit_accounts WHERE linked_circuit_id=?',(circuit_id,)).fetchone()
    pitlane_count2 = 0
    if pitlane_acc2:
        pl2 = conn.execute('SELECT num_pilots FROM circuit_manual_bookings WHERE account_id=? AND booking_date=? AND time_slot=?',
            (pitlane_acc2['id'], booking_date, time_slot)).fetchall()
        pitlane_count2 = sum(r['num_pilots'] for r in pl2)
    total_count = online_count + manual_count + pitlane_count2

    if total_count >= circuit['max_per_session']:
        flash('Esta tanda esta completa.','error')
        conn.close()
        return redirect(url_for('circuit_detail', circuit_id=circuit_id, date=booking_date))

    # Check locked kart from online bookings first, then manual
    locked = conn.execute(
        '''SELECT kt.id, kt.name FROM bookings b
           JOIN kart_types kt ON b.kart_type_id=kt.id
           WHERE b.circuit_id=? AND b.booking_date=? AND b.time_slot=?
           LIMIT 1''',
        (circuit_id, booking_date, time_slot)
    ).fetchone()
    if not locked:
        locked = conn.execute(
            '''SELECT kt.id, kt.name FROM manual_bookings mb
               JOIN kart_types kt ON mb.kart_type_id=kt.id
               WHERE mb.circuit_id=? AND mb.booking_date=? AND mb.time_slot=?
               LIMIT 1''',
            (circuit_id, booking_date, time_slot)
        ).fetchone()

    if locked:
        kart_mix_policy = circuit['kart_mix_policy'] if circuit['kart_mix_policy'] else 'all'
        if kart_mix_policy == 'separate' and kart_type_id:
            locked_group = get_kart_group(locked['name'])
            chosen_kt = conn.execute('SELECT name FROM kart_types WHERE id=?', (kart_type_id,)).fetchone()
            chosen_group = get_kart_group(chosen_kt['name']) if chosen_kt else 'A'
            if chosen_group != locked_group:
                group_label = 'Biplaza/Junior' if locked_group == 'B' else 'Adulto'
                flash(f'Esta tanda esta fijada como "{group_label}". No se pueden mezclar adultos con biplaza/junior.', 'error')
                conn.close()
                return redirect(url_for('circuit_detail', circuit_id=circuit_id, date=booking_date))

    try:
        conn.execute('INSERT INTO bookings (user_id,circuit_id,kart_type_id,booking_date,time_slot) VALUES (?,?,?,?,?)',
            (session['user_id'],circuit_id,kart_type_id,booking_date,time_slot))
        conn.commit()
        flash(f'Reserva confirmada! Tanda el {booking_date} a las {time_slot}.','success')
    except sqlite3.IntegrityError as e:
        if 'user_id' in str(e):
            flash('Ya tienes una reserva en esa tanda.','warning')
        else:
            flash('Ese kart ya esta reservado en esta tanda.','error')
    finally:
        conn.close()
    return redirect(url_for('circuit_detail', circuit_id=circuit_id, date=booking_date))

@app.route('/book_multi', methods=['POST'])
@login_required
def book_multi():
    missing = _check_profile_complete()
    if missing:
        flash(f'Debes completar tu perfil antes de reservar. Faltan: {", ".join(missing)}.', 'error')
        return redirect(url_for('profile_edit'))

    circuit_id  = request.form['circuit_id']
    booking_date = request.form['booking_date']

    # Parse slots from form: slots[0][time_slot], slots[0][kart_type_id], ...
    slots = []
    i = 0
    while f'slots[{i}][time_slot]' in request.form:
        time_slot   = request.form.get(f'slots[{i}][time_slot]', '').strip()
        kart_type_id = request.form.get(f'slots[{i}][kart_type_id]') or None
        if time_slot:
            slots.append({'time_slot': time_slot, 'kart_type_id': kart_type_id})
        i += 1

    if not slots:
        flash('No hay tandas seleccionadas.', 'warning')
        return redirect(url_for('circuit_detail', circuit_id=circuit_id, date=booking_date))

    now = datetime.now()
    conn = get_db()
    circuit = conn.execute('SELECT * FROM circuits WHERE id=?', (circuit_id,)).fetchone()
    confirmed = []
    errors    = []

    for entry in slots:
        time_slot    = entry['time_slot']
        kart_type_id = entry['kart_type_id']

        # Block past slots
        slot_dt = datetime.strptime(f'{booking_date} {time_slot}', '%Y-%m-%d %H:%M')
        if slot_dt <= now:
            errors.append(f'La tanda {time_slot} ya ha pasado.')
            continue

        # Count occupancy
        online_count = conn.execute('SELECT COUNT(*) as cnt FROM bookings WHERE circuit_id=? AND booking_date=? AND time_slot=?',
            (circuit_id, booking_date, time_slot)).fetchone()['cnt']
        manual_rows = conn.execute('SELECT num_pilots FROM manual_bookings WHERE circuit_id=? AND booking_date=? AND time_slot=?',
            (circuit_id, booking_date, time_slot)).fetchall()
        manual_count = sum(r['num_pilots'] for r in manual_rows)
        pitlane_acc2 = conn.execute('SELECT id FROM circuit_accounts WHERE linked_circuit_id=?', (circuit_id,)).fetchone()
        pitlane_count2 = 0
        if pitlane_acc2:
            pl2 = conn.execute('SELECT num_pilots FROM circuit_manual_bookings WHERE account_id=? AND booking_date=? AND time_slot=?',
                (pitlane_acc2['id'], booking_date, time_slot)).fetchall()
            pitlane_count2 = sum(r['num_pilots'] for r in pl2)
        total_count = online_count + manual_count + pitlane_count2

        if total_count >= circuit['max_per_session']:
            errors.append(f'La tanda {time_slot} está completa.')
            continue

        # Check locked kart
        locked = conn.execute(
            '''SELECT kt.id, kt.name FROM bookings b
               JOIN kart_types kt ON b.kart_type_id=kt.id
               WHERE b.circuit_id=? AND b.booking_date=? AND b.time_slot=? LIMIT 1''',
            (circuit_id, booking_date, time_slot)).fetchone()
        if not locked:
            locked = conn.execute(
                '''SELECT kt.id, kt.name FROM manual_bookings mb
                   JOIN kart_types kt ON mb.kart_type_id=kt.id
                   WHERE mb.circuit_id=? AND mb.booking_date=? AND mb.time_slot=? LIMIT 1''',
                (circuit_id, booking_date, time_slot)).fetchone()
        if locked:
            kart_mix_policy = circuit['kart_mix_policy'] if circuit['kart_mix_policy'] else 'all'
            if kart_mix_policy == 'separate' and kart_type_id:
                locked_group = get_kart_group(locked['name'])
                chosen_kt = conn.execute('SELECT name FROM kart_types WHERE id=?', (kart_type_id,)).fetchone()
                chosen_group = get_kart_group(chosen_kt['name']) if chosen_kt else 'A'
                if chosen_group != locked_group:
                    group_label = 'Biplaza/Junior' if locked_group == 'B' else 'Adulto'
                    errors.append(f'Tanda {time_slot}: fijada como "{group_label}". No se pueden mezclar adultos con biplaza/junior.')
                    continue

        try:
            conn.execute('INSERT INTO bookings (user_id,circuit_id,kart_type_id,booking_date,time_slot) VALUES (?,?,?,?,?)',
                (session['user_id'], circuit_id, kart_type_id, booking_date, time_slot))
            conn.commit()
            confirmed.append(time_slot)
        except sqlite3.IntegrityError as e:
            if 'user_id' in str(e):
                errors.append(f'Ya tienes reservada la tanda {time_slot}.')
            else:
                errors.append(f'Error al reservar la tanda {time_slot}.')

    conn.close()

    if confirmed:
        flash(f'✅ Reserva confirmada para {len(confirmed)} tanda{"s" if len(confirmed)!=1 else ""}: {", ".join(confirmed)}.', 'success')
    for err in errors:
        flash(err, 'error')

    return redirect(url_for('circuit_detail', circuit_id=circuit_id, date=booking_date))

@app.route('/cancel_booking/<int:booking_id>', methods=['POST'])
@login_required
def cancel_booking(booking_id):
    conn = get_db()
    booking = conn.execute('SELECT * FROM bookings WHERE id=? AND user_id=?',(booking_id,session['user_id'])).fetchone()
    if booking:
        conn.execute('DELETE FROM bookings WHERE id=?',(booking_id,))
        conn.commit()
        flash('Reserva cancelada.','info')
    else:
        flash('No tienes permiso para cancelar esta reserva.','error')
    conn.close()
    return redirect(url_for('profile'))

@app.route('/api/slot_users')
def api_slot_users():
    circuit_id = request.args.get('circuit_id')
    booking_date = request.args.get('date')
    time_slot = request.args.get('slot')
    conn = get_db()
    bookings = conn.execute('''SELECT u.username, u.full_name, u.karting_level, u.avatar_initial, u.races_completed,
        kt.name as kart_name, kt.engine_cc
        FROM bookings b JOIN users u ON b.user_id=u.id
        LEFT JOIN kart_types kt ON b.kart_type_id=kt.id
        WHERE b.circuit_id=? AND b.booking_date=? AND b.time_slot=?''',(circuit_id,booking_date,time_slot)).fetchall()
    conn.close()
    result = []
    for b in bookings:
        info = get_karting_level_info(b['karting_level'])
        result.append({'username':b['username'],'full_name':b['full_name'],'karting_level':b['karting_level'],
            'avatar_initial':b['avatar_initial'],'races_completed':b['races_completed'],
            'level_color':info['color'],'level_icon':info['icon'],
            'kart_name':b['kart_name'],'engine_cc':b['engine_cc']})
    return jsonify(result)

@app.route('/forgot-password', methods=['GET','POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE LOWER(email)=?',(email,)).fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            expires = datetime.now() + timedelta(hours=1)
            conn.execute('INSERT INTO password_resets (user_id,token,expires_at) VALUES (?,?,?)',(user['id'],token,expires.isoformat()))
            conn.commit()
            reset_link = url_for('reset_password', token=token, _external=True)
            if not send_reset_email(user['email'], user['full_name'], reset_link):
                flash(f'Email no configurado. Usa este enlace: {reset_link}','warning')
            else:
                flash('Te hemos enviado un email con el enlace.','success')
        else:
            flash('Si ese email esta registrado, recibiras un enlace.','success')
        conn.close()
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET','POST'])
def reset_password(token):
    conn = get_db()
    reset = conn.execute('SELECT * FROM password_resets WHERE token=? AND used=0',(token,)).fetchone()
    if not reset:
        flash('Enlace invalido o ya utilizado.','error')
        conn.close()
        return redirect(url_for('login'))
    if datetime.fromisoformat(reset['expires_at']) < datetime.now():
        flash('Este enlace ha expirado.','error')
        conn.close()
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        password = request.form['password']
        confirm = request.form['confirm_password']
        if len(password) < 6:
            flash('Minimo 6 caracteres.','error')
            conn.close()
            return render_template('reset_password.html', token=token)
        if password != confirm:
            flash('Las contrasenas no coinciden.','error')
            conn.close()
            return render_template('reset_password.html', token=token)
        conn.execute('UPDATE users SET password_hash=? WHERE id=?',(hash_password(password),reset['user_id']))
        conn.execute('UPDATE password_resets SET used=1 WHERE token=?',(token,))
        conn.commit()
        conn.close()
        flash('Contrasena actualizada! Ya puedes iniciar sesión.','success')
        return redirect(url_for('login'))
    conn.close()
    return render_template('reset_password.html', token=token)

@app.route('/admin')
@admin_required
def admin_panel():
    conn = get_db()
    users = conn.execute('''SELECT u.*, COUNT(b.id) as total_bookings
        FROM users u LEFT JOIN bookings b ON u.id=b.user_id
        GROUP BY u.id ORDER BY u.created_at DESC''').fetchall()
    today = date.today().isoformat()
    total_bookings = conn.execute('SELECT COUNT(*) as cnt FROM bookings').fetchone()['cnt']
    upcoming_bookings = conn.execute('SELECT COUNT(*) as cnt FROM bookings WHERE booking_date>=?',(today,)).fetchone()['cnt']
    total_users = conn.execute('SELECT COUNT(*) as cnt FROM users WHERE is_admin=0').fetchone()['cnt']
    recent_bookings = conn.execute('''SELECT b.*, u.full_name, u.username, c.name as circuit_name, c.color, c.emoji,
        kt.name as kart_name
        FROM bookings b JOIN users u ON b.user_id=u.id JOIN circuits c ON b.circuit_id=c.id
        LEFT JOIN kart_types kt ON b.kart_type_id=kt.id
        ORDER BY b.created_at DESC LIMIT 20''').fetchall()
    manual_bookings = conn.execute('''SELECT mb.*, c.name as circuit_name, c.color, c.emoji,
        kt.name as kart_name
        FROM manual_bookings mb JOIN circuits c ON mb.circuit_id=c.id
        LEFT JOIN kart_types kt ON mb.kart_type_id=kt.id
        ORDER BY mb.created_at DESC LIMIT 30''').fetchall()
    conn.close()
    return render_template('admin.html', users=users, total_bookings=total_bookings,
        upcoming_bookings=upcoming_bookings, total_users=total_users,
        recent_bookings=recent_bookings, manual_bookings=manual_bookings,
        level_fn=get_karting_level_info, today=today)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    if user_id == session['user_id']:
        flash('No puedes eliminarte a ti mismo.','error')
        return redirect(url_for('admin_panel'))
    conn = get_db()
    conn.execute('DELETE FROM bookings WHERE user_id=?',(user_id,))
    conn.execute('DELETE FROM users WHERE id=?',(user_id,))
    conn.commit()
    conn.close()
    flash('Usuario eliminado.','success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/update_level/<int:user_id>', methods=['POST'])
@admin_required
def admin_update_level(user_id):
    new_level = request.form['level']
    if new_level not in ['Novato','Intermedio','Avanzado','Experto']:
        flash('Nivel no valido.','error')
        return redirect(url_for('admin_panel'))
    conn = get_db()
    conn.execute('UPDATE users SET karting_level=? WHERE id=?',(new_level,user_id))
    conn.commit()
    conn.close()
    flash('Nivel actualizado.','success')
    return redirect(url_for('admin_panel'))

def next_open_date(circuit_name):
    """Return the next date (including today) when the circuit is open."""
    from datetime import timezone, timedelta as td
    spain_tz = timezone(td(hours=1))
    now = datetime.now(spain_tz)
    for delta in range(0, 14):
        check = now + td(days=delta)
        weekday = check.weekday()
        hours = CIRCUIT_HOURS.get(circuit_name, {}).get(weekday, [])
        if not hours:
            continue
        # If it's today, check if there's still time left
        if delta == 0:
            for (oh, om, ch, cm) in hours:
                close_dt = now.replace(hour=ch, minute=cm, second=0, microsecond=0)
                if now < close_dt:
                    return check.date().isoformat()
        else:
            return check.date().isoformat()
    return date.today().isoformat()

@app.route('/api/circuit_slots')
def api_circuit_slots():
    circuit_id = request.args.get('circuit_id')
    booking_date = request.args.get('date', date.today().isoformat())
    conn = get_db()
    circuit = conn.execute('SELECT * FROM circuits WHERE id=?',(circuit_id,)).fetchone()
    if not circuit:
        conn.close()
        return jsonify([])
    try:
        weekday = datetime.strptime(booking_date, '%Y-%m-%d').weekday()
    except:
        weekday = datetime.today().weekday()
    slots = generate_time_slots(circuit['name'], weekday) or generate_time_slots()

    # Get linked pitlane account_id if any
    pitlane_acc = conn.execute('SELECT id FROM circuit_accounts WHERE linked_circuit_id=?',(circuit_id,)).fetchone()
    pitlane_acc_id = pitlane_acc['id'] if pitlane_acc else None

    # Count occupancy per slot
    result = []
    for slot in slots:
        online = conn.execute(
            'SELECT COUNT(*) as cnt FROM bookings WHERE circuit_id=? AND booking_date=? AND time_slot=?',
            (circuit_id, booking_date, slot)
        ).fetchone()['cnt']
        manual_rows = conn.execute(
            'SELECT num_pilots FROM manual_bookings WHERE circuit_id=? AND booking_date=? AND time_slot=?',
            (circuit_id, booking_date, slot)
        ).fetchall()
        manual = sum(r['num_pilots'] for r in manual_rows)
        # Also count pitlane manual bookings
        pitlane = 0
        if pitlane_acc_id:
            pl_rows = conn.execute(
                'SELECT num_pilots FROM circuit_manual_bookings WHERE account_id=? AND booking_date=? AND time_slot=?',
                (pitlane_acc_id, booking_date, slot)
            ).fetchall()
            pitlane = sum(r['num_pilots'] for r in pl_rows)
        total = online + manual + pitlane
        result.append({
            'slot': slot,
            'total': total,
            'available': max(0, circuit['max_per_session'] - total),
            'full': total >= circuit['max_per_session']
        })
    conn.close()
    return jsonify(result)

@app.route('/api/circuits/status')
def api_circuits_status():
    conn = get_db()
    circuits = conn.execute('SELECT id, name FROM circuits').fetchall()
    conn.close()
    result = {}
    for c in circuits:
        open_now, oh, om, ch, cm = is_circuit_open(c['name'])
        if open_now:
            result[c['id']] = {
                'open': True,
                'label': 'Abierto',
                'closes': f'{ch:02d}:{cm:02d}'
            }
        else:
            result[c['id']] = {
                'open': False,
                'label': 'Cerrado',
            }
    return jsonify(result)

@app.route('/api/circuit_availability')
def api_circuit_availability():
    """Return which circuits have available slots on a given date and time range."""
    filter_date = request.args.get('date', date.today().isoformat())
    time_from = request.args.get('from', '08:00')
    time_to = request.args.get('to', '23:45')

    conn = get_db()
    circuits = conn.execute('SELECT * FROM circuits').fetchall()
    result = {}
    for c in circuits:
        # Count slots in time range that still have space
        try:
            sel_weekday = datetime.strptime(filter_date, '%Y-%m-%d').weekday()
        except:
            sel_weekday = datetime.today().weekday()
        slots = generate_time_slots(c['name'], sel_weekday) or generate_time_slots()
        available_slots = 0
        for slot in slots:
            if slot < time_from or slot > time_to:
                continue
            online = conn.execute(
                'SELECT COUNT(*) as cnt FROM bookings WHERE circuit_id=? AND booking_date=? AND time_slot=?',
                (c['id'], filter_date, slot)
            ).fetchone()['cnt']
            manual_rows = conn.execute(
                'SELECT num_pilots FROM manual_bookings WHERE circuit_id=? AND booking_date=? AND time_slot=?',
                (c['id'], filter_date, slot)
            ).fetchall()
            manual = sum(r['num_pilots'] for r in manual_rows)
            if online + manual < c['max_per_session']:
                available_slots += 1
        result[c['id']] = {'available_slots': available_slots, 'has_availability': available_slots > 0}
    conn.close()
    return jsonify(result)

@app.route('/admin/remove_from_slot/<int:booking_id>', methods=['POST'])
@admin_required
def admin_remove_from_slot(booking_id):
    conn = get_db()
    booking = conn.execute('SELECT * FROM bookings WHERE id=?',(booking_id,)).fetchone()
    if booking:
        conn.execute('DELETE FROM bookings WHERE id=?',(booking_id,))
        conn.commit()
        flash('Piloto eliminado de la tanda correctamente.','success')
    else:
        flash('Reserva no encontrada.','error')
    conn.close()
    return redirect(url_for('admin_panel'))

@app.route('/admin/manual_booking', methods=['GET','POST'])
@admin_required
def admin_manual_booking():
    conn = get_db()
    circuits = conn.execute('SELECT * FROM circuits').fetchall()
    if request.method == 'POST':
        circuit_id = request.form['circuit_id']
        booking_date = request.form['booking_date']
        time_slot = request.form['time_slot']
        num_pilots = int(request.form.get('num_pilots', 1))
        contact_name = request.form['contact_name'].strip()
        contact_phone = request.form.get('contact_phone','').strip()
        contact_email = request.form.get('contact_email','').strip()
        kart_type_id = request.form.get('kart_type_id') or None
        notes = request.form.get('notes','').strip()

        # Block past date/time
        slot_dt = datetime.strptime(f'{booking_date} {time_slot}', '%Y-%m-%d %H:%M')
        if slot_dt <= datetime.now():
            flash('No se puede añadir una reserva en una fecha u hora que ya ha pasado.', 'error')
            kart_types = conn.execute('SELECT * FROM kart_types WHERE circuit_id=?',(circuit_id,)).fetchall()
            conn.close()
            return render_template('admin_manual_booking.html', circuits=circuits, kart_types=kart_types, form=request.form)

        # Check locked kart type
        locked = conn.execute(
            '''SELECT kt.id, kt.name FROM bookings b
               JOIN kart_types kt ON b.kart_type_id=kt.id
               WHERE b.circuit_id=? AND b.booking_date=? AND b.time_slot=?
               LIMIT 1''',
            (circuit_id, booking_date, time_slot)
        ).fetchone()
        if not locked:
            locked = conn.execute(
                '''SELECT kt.id, kt.name FROM manual_bookings mb
                   JOIN kart_types kt ON mb.kart_type_id=kt.id
                   WHERE mb.circuit_id=? AND mb.booking_date=? AND mb.time_slot=?
                   LIMIT 1''',
                (circuit_id, booking_date, time_slot)
            ).fetchone()
        if locked and kart_type_id:
            circuit_row = conn.execute('SELECT kart_mix_policy FROM circuits WHERE id=?', (circuit_id,)).fetchone()
            kart_mix_policy = circuit_row['kart_mix_policy'] if circuit_row and circuit_row['kart_mix_policy'] else 'all'
            if kart_mix_policy == 'separate':
                locked_group = get_kart_group(locked['name'])
                chosen_kt = conn.execute('SELECT name FROM kart_types WHERE id=?', (kart_type_id,)).fetchone()
                chosen_group = get_kart_group(chosen_kt['name']) if chosen_kt else 'A'
                if chosen_group != locked_group:
                    group_label = 'Biplaza/Junior' if locked_group == 'B' else 'Adulto'
                    flash(f'Esta tanda esta fijada como "{group_label}". No se pueden mezclar adultos con biplaza/junior.', 'error')
                    kart_types = conn.execute('SELECT * FROM kart_types WHERE circuit_id=?',(circuit_id,)).fetchall()
                    conn.close()
                    return render_template('admin_manual_booking.html', circuits=circuits, kart_types=kart_types, form=request.form)

        # Check capacity
        circuit = conn.execute('SELECT * FROM circuits WHERE id=?',(circuit_id,)).fetchone()
        online_count = conn.execute('SELECT COUNT(*) as cnt FROM bookings WHERE circuit_id=? AND booking_date=? AND time_slot=?',
            (circuit_id,booking_date,time_slot)).fetchone()['cnt']
        manual_rows = conn.execute('SELECT num_pilots FROM manual_bookings WHERE circuit_id=? AND booking_date=? AND time_slot=?',
            (circuit_id,booking_date,time_slot)).fetchall()
        manual_count = sum(r['num_pilots'] for r in manual_rows)
        total = online_count + manual_count

        if total + num_pilots > circuit['max_per_session']:
            remaining = circuit['max_per_session'] - total
            flash(f'Solo quedan {remaining} plazas en esa tanda. No se pueden añadir {num_pilots} pilotos.','error')
            kart_types = conn.execute('SELECT * FROM kart_types WHERE circuit_id=?',(circuit_id,)).fetchall()
            conn.close()
            return render_template('admin_manual_booking.html', circuits=circuits,
                kart_types=kart_types, form=request.form)

        conn.execute('''INSERT INTO manual_bookings
            (circuit_id, kart_type_id, booking_date, time_slot, num_pilots, contact_name, contact_phone, contact_email, notes, created_by)
            VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (circuit_id, kart_type_id, booking_date, time_slot, num_pilots,
             contact_name, contact_phone, contact_email, notes, session['user_id']))
        conn.commit()
        conn.close()
        flash(f'Reserva manual de {num_pilots} piloto{"s" if num_pilots>1 else ""} añadida correctamente para el {booking_date} a las {time_slot}.','success')
        return redirect(url_for('admin_panel'))

    # GET — load kart types for first circuit
    kart_types = conn.execute('SELECT * FROM kart_types WHERE circuit_id=?',(circuits[0]['id'],)).fetchall() if circuits else []
    conn.close()
    return render_template('admin_manual_booking.html', circuits=circuits, kart_types=kart_types, form={})

@app.route('/api/kart_types/<int:circuit_id>')
def api_kart_types(circuit_id):
    conn = get_db()
    karts = conn.execute('SELECT * FROM kart_types WHERE circuit_id=?',(circuit_id,)).fetchall()
    conn.close()
    return jsonify([dict(k) for k in karts])

@app.route('/admin/delete_manual/<int:booking_id>', methods=['POST'])
@admin_required
def admin_delete_manual(booking_id):
    conn = get_db()
    conn.execute('DELETE FROM manual_bookings WHERE id=?',(booking_id,))
    conn.commit()
    conn.close()
    flash('Reserva manual eliminada.','info')
    return redirect(url_for('admin_panel'))

# ── PITLANE ROUTES ──

WEEKDAY_NAMES = ['Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo']

def pitlane_required(f):
    @wraps(f)
    def d(*a, **kw):
        if 'circuit_id' not in session:
            return redirect(url_for('pitlane'))
        return f(*a, **kw)
    return d

@app.route('/pitlane', methods=['GET','POST'])
def pitlane():
    if session.get('user_id') and not session.get('is_admin'):
        flash('Debes cerrar sesión como piloto antes de acceder al área de pitlane.', 'error')
        return redirect(url_for('index'))
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'login':
            username = request.form['username'].strip()
            password = request.form['password']
            conn = get_db()
            acc = conn.execute(
                'SELECT * FROM circuit_accounts WHERE username=? AND password_hash=?',
                (username, hash_password(password))
            ).fetchone()
            conn.close()
            if acc:
                session['circuit_id'] = acc['id']
                session['circuit_name'] = acc['circuit_name']
                session['circuit_username'] = acc['username']
                flash(f'Bienvenido, {acc["circuit_name"]}.', 'success')
                return redirect(url_for('pitlane_dashboard'))
            else:
                flash('Usuario o contraseña incorrectos.', 'error')

        elif action == 'register':
            username = request.form['username'].strip()
            circuit_name = request.form['circuit_name'].strip()
            city = request.form['city'].strip()
            password = request.form['password']
            if not username or not circuit_name or not city or not password:
                flash('Todos los campos son obligatorios.', 'error')
            elif len(password) < 6:
                flash('La contraseña debe tener al menos 6 caracteres.', 'error')
            else:
                conn = get_db()
                try:
                    conn.execute(
                        'INSERT INTO circuit_accounts (username, circuit_name, city, password_hash) VALUES (?,?,?,?)',
                        (username, circuit_name, city, hash_password(password))
                    )
                    conn.commit()
                    flash('Cuenta creada. Ya puedes iniciar sesión.', 'success')
                    return redirect(url_for('pitlane'))
                except sqlite3.IntegrityError:
                    flash('Ese nombre de usuario ya está en uso.', 'error')
                finally:
                    conn.close()

    return render_template('pitlane.html')

@app.route('/api/pitlane/slots')
def api_pitlane_slots():
    account_id = request.args.get('account_id')
    booking_date = request.args.get('date', date.today().isoformat())
    conn = get_db()
    info = conn.execute('SELECT * FROM circuit_info WHERE account_id=?', (account_id,)).fetchone()
    max_per = info['max_per_session'] if info else 12
    try:
        weekday = datetime.strptime(booking_date, '%Y-%m-%d').weekday()
    except:
        weekday = datetime.today().weekday()
    # Check override
    override = conn.execute(
        'SELECT * FROM circuit_schedule_override WHERE account_id=? AND override_date=?',
        (account_id, booking_date)
    ).fetchone()
    if override:
        if override['is_closed']:
            conn.close(); return jsonify([])
        ranges = [(override['open_time'], override['close_time'])]
    else:
        sched = conn.execute(
            'SELECT * FROM circuit_schedule WHERE account_id=? AND weekday=?', (account_id, weekday)
        ).fetchone()
        if not sched or sched['is_closed'] or not sched['open_time']:
            conn.close(); return jsonify([])
        ranges = [(sched['open_time'], sched['close_time'])]

    slots = []
    for (open_t, close_t) in ranges:
        try:
            cur = datetime.strptime(open_t, '%H:%M')
            end = datetime.strptime(close_t, '%H:%M')
            while cur <= end:
                slots.append(cur.strftime('%H:%M'))
                cur += timedelta(minutes=15)
        except: pass

    # Get linked main circuit_id and kart_mix_policy
    acc = conn.execute('SELECT linked_circuit_id FROM circuit_accounts WHERE id=?',(account_id,)).fetchone()
    linked_cid = acc['linked_circuit_id'] if acc else None
    kart_mix_policy = 'all'
    if linked_cid:
        cr = conn.execute('SELECT kart_mix_policy FROM circuits WHERE id=?', (linked_cid,)).fetchone()
        if cr and cr['kart_mix_policy']:
            kart_mix_policy = cr['kart_mix_policy']

    result = []
    for slot in slots:
        # PitLane manual bookings
        pitlane_bk = conn.execute(
            'SELECT COALESCE(SUM(num_pilots),0) as total FROM circuit_manual_bookings WHERE account_id=? AND booking_date=? AND time_slot=?',
            (account_id, booking_date, slot)
        ).fetchone()['total']
        # Online pilot bookings from main system
        online_bk = 0
        admin_bk = 0
        if linked_cid:
            online_bk = conn.execute(
                'SELECT COUNT(*) as cnt FROM bookings WHERE circuit_id=? AND booking_date=? AND time_slot=?',
                (linked_cid, booking_date, slot)
            ).fetchone()['cnt']
            admin_rows = conn.execute(
                'SELECT num_pilots FROM manual_bookings WHERE circuit_id=? AND booking_date=? AND time_slot=?',
                (linked_cid, booking_date, slot)
            ).fetchall()
            admin_bk = sum(r['num_pilots'] for r in admin_rows)
        total = pitlane_bk + online_bk + admin_bk
        available = max(0, max_per - total)

        # Determine locked kart group for this slot
        locked_kart_group = None
        if kart_mix_policy == 'separate' and linked_cid:
            # Check online pilot bookings
            first_online = conn.execute(
                '''SELECT kt.name FROM bookings b JOIN kart_types kt ON b.kart_type_id=kt.id
                   WHERE b.circuit_id=? AND b.booking_date=? AND b.time_slot=? LIMIT 1''',
                (linked_cid, booking_date, slot)
            ).fetchone()
            if first_online:
                locked_kart_group = get_kart_group(first_online['name'])
            else:
                # Check admin manual bookings
                first_admin = conn.execute(
                    '''SELECT kt.name FROM manual_bookings mb JOIN kart_types kt ON mb.kart_type_id=kt.id
                       WHERE mb.circuit_id=? AND mb.booking_date=? AND mb.time_slot=? LIMIT 1''',
                    (linked_cid, booking_date, slot)
                ).fetchone()
                if first_admin:
                    locked_kart_group = get_kart_group(first_admin['name'])
                else:
                    # Check pitlane manual bookings
                    first_pitlane = conn.execute(
                        '''SELECT kt.name FROM circuit_manual_bookings cmb JOIN kart_types kt ON cmb.kart_type_id=kt.id
                           WHERE cmb.account_id=? AND cmb.booking_date=? AND cmb.time_slot=? LIMIT 1''',
                        (account_id, booking_date, slot)
                    ).fetchone()
                    if first_pitlane:
                        locked_kart_group = get_kart_group(first_pitlane['name'])

        result.append({
            'slot': slot, 'total': total, 'available': available,
            'full': total >= max_per, 'max': max_per,
            'locked_kart_group': locked_kart_group,
            'kart_mix_policy': kart_mix_policy,
        })
    conn.close()
    return jsonify(result)

@app.route('/api/pitlane/kart_types/<int:account_id>')
def api_pitlane_kart_types(account_id):
    conn = get_db()
    linked = conn.execute('SELECT linked_circuit_id FROM circuit_accounts WHERE id=?', (account_id,)).fetchone()
    if linked and linked['linked_circuit_id']:
        karts = conn.execute('SELECT * FROM kart_types WHERE circuit_id=?', (linked['linked_circuit_id'],)).fetchall()
    else:
        karts = []
    conn.close()
    return jsonify([dict(k) for k in karts])

@app.route('/pitlane/kart-types', methods=['POST'])
@pitlane_required
def pitlane_save_kart_type():
    acc_id = session['circuit_id']
    name = request.form.get('kt_name','').strip()
    engine_cc = int(request.form.get('kt_cc', 0) or 0)
    description = request.form.get('kt_desc','').strip()
    min_age = int(request.form.get('kt_age', 0) or 0)
    price_per_session = float(request.form.get('kt_price', 0) or 0)
    if name:
        conn = get_db()
        linked = conn.execute('SELECT linked_circuit_id FROM circuit_accounts WHERE id=?', (acc_id,)).fetchone()
        if linked and linked['linked_circuit_id']:
            conn.execute('INSERT INTO kart_types (circuit_id,name,engine_cc,description,min_age,price_per_session) VALUES (?,?,?,?,?,?)',
                (linked['linked_circuit_id'], name, engine_cc, description, min_age, price_per_session))
            conn.commit()
            flash('Tipo de kart añadido.', 'success')
        else:
            flash('Este circuito no está vinculado a ningún kartódromo.', 'error')
        conn.close()
    return redirect(url_for('pitlane_dashboard') + '#info')

@app.route('/pitlane/kart-types/delete/<int:kt_id>', methods=['POST'])
@pitlane_required
def pitlane_delete_kart_type(kt_id):
    acc_id = session['circuit_id']
    conn = get_db()
    linked = conn.execute('SELECT linked_circuit_id FROM circuit_accounts WHERE id=?', (acc_id,)).fetchone()
    if linked and linked['linked_circuit_id']:
        conn.execute('DELETE FROM kart_types WHERE id=? AND circuit_id=?', (kt_id, linked['linked_circuit_id']))
        conn.commit()
    conn.close()
    flash('Tipo de kart eliminado.', 'info')
    return redirect(url_for('pitlane_dashboard') + '#info')

@app.route('/pitlane/kart-types/edit/<int:kt_id>', methods=['POST'])
@pitlane_required
def pitlane_edit_kart_type(kt_id):
    acc_id = session['circuit_id']
    name = request.form.get('kt_name', '').strip()
    engine_cc = int(request.form.get('kt_cc', 0) or 0)
    description = request.form.get('kt_desc', '').strip()
    min_age = int(request.form.get('kt_age', 0) or 0)
    price_per_session = float(request.form.get('kt_price', 0) or 0)
    if name:
        conn = get_db()
        linked = conn.execute('SELECT linked_circuit_id FROM circuit_accounts WHERE id=?', (acc_id,)).fetchone()
        if linked and linked['linked_circuit_id']:
            conn.execute(
                'UPDATE kart_types SET name=?, engine_cc=?, description=?, min_age=?, price_per_session=? WHERE id=? AND circuit_id=?',
                (name, engine_cc, description, min_age, price_per_session, kt_id, linked['linked_circuit_id'])
            )
            conn.commit()
            flash('Tipo de kart actualizado.', 'success')
        conn.close()
    return redirect(url_for('pitlane_dashboard') + '#info')

@app.route('/pitlane/kart-mix-policy', methods=['POST'])
@pitlane_required
def pitlane_save_kart_mix_policy():
    acc_id = session['circuit_id']
    policy = request.form.get('kart_mix_policy', 'all')
    if policy not in ('all', 'separate'):
        policy = 'all'
    conn = get_db()
    linked = conn.execute('SELECT linked_circuit_id FROM circuit_accounts WHERE id=?', (acc_id,)).fetchone()
    if linked and linked['linked_circuit_id']:
        conn.execute('UPDATE circuits SET kart_mix_policy=? WHERE id=?', (policy, linked['linked_circuit_id']))
        conn.commit()
        label = 'Todos juntos' if policy == 'all' else 'Adulto separado de biplaza/junior'
        flash(f'Compatibilidad de karts actualizada: {label}.', 'success')
    else:
        flash('Este circuito no esta vinculado a ningun kartodromo.', 'error')
    conn.close()
    return redirect(url_for('pitlane_dashboard') + '#info')

@app.route('/pitlane/dashboard')
@pitlane_required
def pitlane_dashboard():
    conn = get_db()
    acc_id = session['circuit_id']
    info = conn.execute('SELECT * FROM circuit_info WHERE account_id=?', (acc_id,)).fetchone()
    schedule = conn.execute('SELECT * FROM circuit_schedule WHERE account_id=? ORDER BY weekday', (acc_id,)).fetchall()
    today = date.today().isoformat()

    # Manual bookings by the circuit
    manual_bookings = conn.execute(
        '''SELECT cmb.*, kt.name as kart_name FROM circuit_manual_bookings cmb
           LEFT JOIN kart_types kt ON cmb.kart_type_id=kt.id
           WHERE cmb.account_id=? ORDER BY cmb.booking_date DESC, cmb.time_slot DESC''',
        (acc_id,)
    ).fetchall()

    # Online bookings by pilots for the linked circuit
    linked = conn.execute('SELECT linked_circuit_id FROM circuit_accounts WHERE id=?', (acc_id,)).fetchone()
    online_bookings = []
    if linked and linked['linked_circuit_id']:
        circuit_id = linked['linked_circuit_id']
        rows = conn.execute('''
            SELECT b.id, b.booking_date, b.time_slot, b.created_at,
                   u.full_name as contact_name, u.email as contact_email,
                   u."teléfono" as contact_phone,
                   kt.name as kart_name
            FROM bookings b
            JOIN users u ON b.user_id = u.id
            LEFT JOIN kart_types kt ON b.kart_type_id = kt.id
            WHERE b.circuit_id = ?
            ORDER BY b.booking_date DESC, b.time_slot DESC
        ''', (circuit_id,)).fetchall()
        online_bookings = [dict(r, num_pilots=1, notes='—', source='pilot') for r in rows]

    # Merge: tag manual bookings with source
    manual_list = [dict(b, source='manual') for b in manual_bookings]

    # Combined and sorted
    all_bookings = sorted(manual_list + online_bookings,
        key=lambda x: (x['booking_date'], x['time_slot']), reverse=True)

    overrides = conn.execute(
        'SELECT * FROM circuit_schedule_override WHERE account_id=? AND override_date >= ? ORDER BY override_date',
        (acc_id, today)
    ).fetchall()
    kart_types_raw = []
    kart_mix_policy = 'all'
    if linked and linked['linked_circuit_id']:
        kart_types_raw = conn.execute('SELECT * FROM kart_types WHERE circuit_id=?', (linked['linked_circuit_id'],)).fetchall()
        circuit_row = conn.execute('SELECT kart_mix_policy FROM circuits WHERE id=?', (linked['linked_circuit_id'],)).fetchone()
        if circuit_row and circuit_row['kart_mix_policy']:
            kart_mix_policy = circuit_row['kart_mix_policy']
    kart_types = [dict(k) for k in kart_types_raw]

    # Build calendar data: { "YYYY-MM-DD": [ {slot, pilots, source, contact, kart}, ... ] }
    from collections import defaultdict
    _cal = defaultdict(list)
    for b in all_bookings:
        _cal[b['booking_date']].append({
            'slot': b['time_slot'],
            'pilots': b.get('num_pilots', 1) or 1,
            'source': b.get('source', 'manual'),
            'contact': b.get('contact_name') or '',
            'kart': b.get('kart_name') or '',
        })
    for k in _cal:
        _cal[k].sort(key=lambda x: x['slot'])
    import json as _json
    calendar_data = _json.dumps(dict(_cal))

    conn.close()
    return render_template('pitlane_dashboard.html',
        info=info, schedule=schedule, bookings=all_bookings, kart_types=kart_types,
        overrides=overrides, weekday_names=WEEKDAY_NAMES, today=today,
        kart_mix_policy=kart_mix_policy, calendar_data=calendar_data)

@app.route('/pitlane/info', methods=['POST'])
@pitlane_required
def pitlane_save_info():
    acc_id = session['circuit_id']
    data = {
        'display_name': request.form.get('display_name','').strip(),
        'address': request.form.get('address','').strip(),
        'city': request.form.get('city','').strip(),
        'length_m': int(request.form.get('length_m', 0) or 0),
        'max_per_session': int(request.form.get('max_per_session', 12) or 12),
        'website': request.form.get('website','').strip(),
        'phone': request.form.get('phone','').strip(),
        'description': request.form.get('description','').strip(),
        'price_per_session': float(request.form.get('price_per_session', 0) or 0),
    }
    conn = get_db()
    existing = conn.execute('SELECT id FROM circuit_info WHERE account_id=?', (acc_id,)).fetchone()
    if existing:
        conn.execute('''UPDATE circuit_info SET display_name=?,address=?,city=?,length_m=?,
            max_per_session=?,website=?,phone=?,description=?,price_per_session=?,updated_at=CURRENT_TIMESTAMP
            WHERE account_id=?''',
            (data['display_name'],data['address'],data['city'],data['length_m'],
             data['max_per_session'],data['website'],data['phone'],data['description'],data['price_per_session'],acc_id))
    else:
        conn.execute('''INSERT INTO circuit_info (account_id,display_name,address,city,length_m,
            max_per_session,website,phone,description,price_per_session) VALUES (?,?,?,?,?,?,?,?,?,?)''',
            (acc_id,data['display_name'],data['address'],data['city'],data['length_m'],
             data['max_per_session'],data['website'],data['phone'],data['description'],data['price_per_session']))
    conn.commit(); conn.close()
    flash('Información del circuito guardada.', 'success')
    return redirect(url_for('pitlane_dashboard') + '#info')

@app.route('/pitlane/schedule', methods=['POST'])
@pitlane_required
def pitlane_save_schedule():
    acc_id = session['circuit_id']
    conn = get_db()
    for wd in range(7):
        is_closed = 1 if request.form.get(f'closed_{wd}') else 0
        open_t = request.form.get(f'open_{wd}', '').strip()
        close_t = request.form.get(f'close_{wd}', '').strip()
        existing = conn.execute('SELECT id FROM circuit_schedule WHERE account_id=? AND weekday=?', (acc_id, wd)).fetchone()
        if existing:
            conn.execute('UPDATE circuit_schedule SET open_time=?,close_time=?,is_closed=? WHERE account_id=? AND weekday=?',
                (open_t, close_t, is_closed, acc_id, wd))
        else:
            conn.execute('INSERT INTO circuit_schedule (account_id,weekday,open_time,close_time,is_closed) VALUES (?,?,?,?,?)',
                (acc_id, wd, open_t, close_t, is_closed))
    conn.commit(); conn.close()
    flash('Horario semanal guardado.', 'success')
    return redirect(url_for('pitlane_dashboard') + '#schedule')

@app.route('/pitlane/override', methods=['POST'])
@pitlane_required
def pitlane_save_override():
    acc_id = session['circuit_id']
    override_date = request.form.get('override_date','').strip()
    is_closed = 1 if request.form.get('override_closed') else 0
    open_t = request.form.get('override_open','').strip()
    close_t = request.form.get('override_close','').strip()
    reason = request.form.get('override_reason','').strip()
    if not override_date:
        flash('Debes indicar una fecha.', 'error'); return redirect(url_for('pitlane_dashboard'))
    conn = get_db()
    conn.execute('''INSERT INTO circuit_schedule_override (account_id,override_date,open_time,close_time,is_closed,reason)
        VALUES (?,?,?,?,?,?) ON CONFLICT(account_id,override_date) DO UPDATE SET
        open_time=excluded.open_time,close_time=excluded.close_time,
        is_closed=excluded.is_closed,reason=excluded.reason''',
        (acc_id, override_date, open_t, close_t, is_closed, reason))
    conn.commit(); conn.close()
    flash(f'Horario especial para {override_date} guardado.', 'success')
    return redirect(url_for('pitlane_dashboard') + '#schedule')

@app.route('/pitlane/override/delete/<int:oid>', methods=['POST'])
@pitlane_required
def pitlane_delete_override(oid):
    conn = get_db()
    conn.execute('DELETE FROM circuit_schedule_override WHERE id=? AND account_id=?', (oid, session['circuit_id']))
    conn.commit(); conn.close()
    flash('Horario especial eliminado.', 'info')
    return redirect(url_for('pitlane_dashboard') + '#schedule')

@app.route('/pitlane/booking', methods=['POST'])
@pitlane_required
def pitlane_add_booking():
    acc_id = session['circuit_id']
    booking_date = request.form.get('booking_date','').strip()
    time_slot = request.form.get('time_slot','').strip()
    num_pilots = int(request.form.get('num_pilots', 1) or 1)
    kart_type_id = request.form.get('kart_type_id','').strip() or None
    contact_name = request.form.get('contact_name','').strip()
    contact_phone = request.form.get('contact_phone','').strip()
    contact_email = request.form.get('contact_email','').strip()
    notes = request.form.get('notes','').strip()
    if not booking_date or not time_slot or not contact_name:
        flash('Fecha, hora y nombre de contacto son obligatorios.', 'error')
        return redirect(url_for('pitlane_dashboard'))
    conn = get_db()

    # Validate kart compatibility if policy is 'separate'
    linked = conn.execute('SELECT linked_circuit_id FROM circuit_accounts WHERE id=?', (acc_id,)).fetchone()
    linked_cid = linked['linked_circuit_id'] if linked else None
    if linked_cid and kart_type_id:
        circuit_row = conn.execute('SELECT kart_mix_policy FROM circuits WHERE id=?', (linked_cid,)).fetchone()
        if circuit_row and circuit_row['kart_mix_policy'] == 'separate':
            chosen_kt = conn.execute('SELECT name FROM kart_types WHERE id=?', (kart_type_id,)).fetchone()
            chosen_group = get_kart_group(chosen_kt['name']) if chosen_kt else 'A'
            # Find locked group from existing bookings in this slot
            locked_group = None
            first = conn.execute(
                '''SELECT kt.name FROM bookings b JOIN kart_types kt ON b.kart_type_id=kt.id
                   WHERE b.circuit_id=? AND b.booking_date=? AND b.time_slot=? LIMIT 1''',
                (linked_cid, booking_date, time_slot)
            ).fetchone()
            if first:
                locked_group = get_kart_group(first['name'])
            else:
                first = conn.execute(
                    '''SELECT kt.name FROM manual_bookings mb JOIN kart_types kt ON mb.kart_type_id=kt.id
                       WHERE mb.circuit_id=? AND mb.booking_date=? AND mb.time_slot=? LIMIT 1''',
                    (linked_cid, booking_date, time_slot)
                ).fetchone()
                if first:
                    locked_group = get_kart_group(first['name'])
                else:
                    first = conn.execute(
                        '''SELECT kt.name FROM circuit_manual_bookings cmb JOIN kart_types kt ON cmb.kart_type_id=kt.id
                           WHERE cmb.account_id=? AND cmb.booking_date=? AND cmb.time_slot=? LIMIT 1''',
                        (acc_id, booking_date, time_slot)
                    ).fetchone()
                    if first:
                        locked_group = get_kart_group(first['name'])
            if locked_group and chosen_group != locked_group:
                group_label = 'Biplaza/Junior' if locked_group == 'B' else 'Adulto'
                conn.close()
                flash(f'Esta tanda ya está fijada como "{group_label}". No se pueden mezclar tipos de kart.', 'error')
                return redirect(url_for('pitlane_dashboard'))

    conn.execute('''INSERT INTO circuit_manual_bookings
        (account_id,booking_date,time_slot,num_pilots,contact_name,contact_phone,contact_email,notes,kart_type_id)
        VALUES (?,?,?,?,?,?,?,?,?)''',
        (acc_id, booking_date, time_slot, num_pilots, contact_name, contact_phone, contact_email, notes, kart_type_id))
    conn.commit(); conn.close()
    flash(f'Reserva añadida para el {booking_date} a las {time_slot}.', 'success')
    return redirect(url_for('pitlane_dashboard') + '#bookings')

@app.route('/pitlane/booking/delete/<int:bid>', methods=['POST'])
@pitlane_required
def pitlane_delete_booking(bid):
    conn = get_db()
    conn.execute('DELETE FROM circuit_manual_bookings WHERE id=? AND account_id=?', (bid, session['circuit_id']))
    conn.commit(); conn.close()
    flash('Reserva eliminada.', 'info')
    return redirect(url_for('pitlane_dashboard') + '#bookings')

@app.route('/pitlane/booking/delete-pilot/<int:bid>', methods=['POST'])
@pitlane_required
def pitlane_delete_pilot_booking(bid):
    conn = get_db()
    linked = conn.execute('SELECT linked_circuit_id FROM circuit_accounts WHERE id=?', (session['circuit_id'],)).fetchone()
    if linked and linked['linked_circuit_id']:
        conn.execute('DELETE FROM bookings WHERE id=? AND circuit_id=?', (bid, linked['linked_circuit_id']))
        conn.commit()
        flash('Reserva del piloto eliminada.', 'info')
    else:
        flash('No tienes permiso para eliminar esta reserva.', 'error')
    conn.close()
    return redirect(url_for('pitlane_dashboard') + '#bookings')

@app.route('/pitlane/logout')
def pitlane_logout():
    session.pop('circuit_id', None)
    session.pop('circuit_name', None)
    session.pop('circuit_username', None)
    flash('Sesión cerrada.', 'info')
    return redirect(url_for('pitlane'))

@app.route('/auth/google')
def google_login():
    if not os.environ.get('GOOGLE_CLIENT_ID'):
        flash('El inicio de sesión con Google no está configurado.', 'error')
        return redirect(url_for('login'))
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/auth/google/callback')
def google_callback():
    if not os.environ.get('GOOGLE_CLIENT_ID'):
        flash('El inicio de sesión con Google no está configurado.', 'error')
        return redirect(url_for('login'))
    try:
        token = google.authorize_access_token()
    except Exception:
        flash('Error al autenticar con Google. Inténtalo de nuevo.', 'error')
        return redirect(url_for('login'))

    userinfo = token.get('userinfo')
    if not userinfo:
        flash('No se pudo obtener información de Google.', 'error')
        return redirect(url_for('login'))

    google_id = userinfo.get('sub')
    email = userinfo.get('email', '')
    given_name = userinfo.get('given_name', '')
    family_name = userinfo.get('family_name', '')

    conn = get_db()

    # Existing Google-linked user
    user = conn.execute('SELECT * FROM users WHERE google_id=?', (google_id,)).fetchone()
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['is_admin'] = bool(user['is_admin'])
        conn.close()
        flash(f'Bienvenido, {user["full_name"].split()[0]}!', 'success')
        return redirect(url_for('admin_panel') if user['is_admin'] else url_for('index'))

    # Email already registered — link Google account
    user = conn.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
    if user:
        conn.execute('UPDATE users SET google_id=? WHERE id=?', (google_id, user['id']))
        conn.commit()
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['is_admin'] = bool(user['is_admin'])
        conn.close()
        flash(f'Bienvenido, {user["full_name"].split()[0]}! Cuenta vinculada con Google.', 'success')
        return redirect(url_for('admin_panel') if user['is_admin'] else url_for('index'))

    # New user — create account from Google data
    username_base = email.split('@')[0] if email else 'piloto'
    username = username_base
    suffix = 1
    while conn.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone():
        username = f'{username_base}{suffix}'
        suffix += 1

    avatar_initial = given_name[0].upper() if given_name else (email[0].upper() if email else 'P')
    try:
        conn.execute('''INSERT INTO users
            (username, email, password_hash, full_name, apellido, avatar_initial, google_id)
            VALUES (?,?,?,?,?,?,?)''',
            (username, email, '', given_name or username, family_name, avatar_initial, google_id))
        conn.commit()
        user = conn.execute('SELECT * FROM users WHERE google_id=?', (google_id,)).fetchone()
        session['user_id'] = user['id']
        session['username'] = user['username']
        session['is_admin'] = False
        conn.close()
        flash(f'Bienvenido a KARTNATION, {given_name or username}! Por favor completa tu perfil con tu fecha de nacimiento.', 'success')
        return redirect(url_for('profile_edit'))
    except sqlite3.IntegrityError:
        conn.close()
        flash('Error al crear la cuenta. El email ya está en uso.', 'error')
        return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
