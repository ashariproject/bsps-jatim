"""
geocode_kantordesa.py
Mengisi lat/lng null di data_desa_t2.json dengan mencari:
  1. Kantor/Balai Desa via Overpass API (OpenStreetMap) — paling akurat
  2. Nominatim: "Kantor Desa X, Kecamatan Y"
  3. Nominatim: "Balai Desa X, ..."
  4. Nominatim: Nama desa + kecamatan + kabupaten
  5. Fallback: nama kecamatan saja (perkiraan)
"""
import json, time, urllib.request, urllib.parse, os

INPUT_FILE  = 'data_desa_t2.json'
OUTPUT_FILE = 'data_desa_t2.json'
DELAY       = 1.2   # Nominatim: max 1 req/detik
HEADERS     = {'User-Agent': 'BSPS-Dashboard-Geocoder/2.0 (bsps-jatim2026.my.id)'}

def overpass_kantordesa(desa):
    """Cari Kantor/Balai Desa via Overpass API"""
    desa_clean = desa.title()
    query = f"""[out:json][timeout:10];
area["name"="Jawa Timur"]["admin_level"="4"]->.jatim;
(
  node(area.jatim)["amenity"="townhall"]["name"~"{desa_clean}",i];
  node(area.jatim)["office"="government"]["name"~"{desa_clean}",i];
);
out center 1;"""
    try:
        data = urllib.parse.urlencode({'data': query}).encode()
        req = urllib.request.Request('https://overpass-api.de/api/interpreter', data=data, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as r:
            res = json.loads(r.read())
        els = res.get('elements', [])
        if els:
            el = els[0]
            lat = el.get('lat') or el.get('center', {}).get('lat')
            lng = el.get('lon') or el.get('center', {}).get('lon')
            if lat and lng:
                return round(float(lat), 6), round(float(lng), 6), 'overpass'
    except:
        pass
    return None, None, None

def nominatim(q):
    """Geocode query via Nominatim"""
    try:
        params = urllib.parse.urlencode({
            'q': q, 'format': 'json', 'limit': 1,
            'countrycodes': 'id',
            'viewbox': '110.8,-8.9,114.9,-6.8', 'bounded': 1
        })
        req = urllib.request.Request(
            f"https://nominatim.openstreetmap.org/search?{params}", headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data:
            return round(float(data[0]['lat']), 6), round(float(data[0]['lon']), 6)
    except:
        pass
    return None, None

def get_koordinat(desa, kec, kab):
    kab_c = kab.replace('KAB. ', '').replace('KOTA ', '').title()
    kec_c = kec.title()
    d_c   = desa.title()

    # 1. Overpass: Kantor Desa via OSM
    lat, lng, src = overpass_kantordesa(desa)
    time.sleep(DELAY)
    if lat: return lat, lng, src

    # 2-6. Nominatim bertingkat
    queries = [
        (f"Kantor Desa {d_c}, Kecamatan {kec_c}, {kab_c}, Jawa Timur",   'kantordesa'),
        (f"Balai Desa {d_c}, {kec_c}, {kab_c}, Jawa Timur",              'balaidesa'),
        (f"Kantor Kepala Desa {d_c}, {kab_c}, Jawa Timur",               'kantordesa'),
        (f"Desa {d_c}, Kecamatan {kec_c}, Kabupaten {kab_c}, Jawa Timur",'desa'),
        (f"{d_c}, {kec_c}, {kab_c}, Jawa Timur, Indonesia",              'desa'),
        (f"Kecamatan {kec_c}, {kab_c}, Jawa Timur",                      'kecamatan'),
    ]
    for q, src in queries:
        lat, lng = nominatim(q)
        time.sleep(DELAY)
        if lat:
            return lat, lng, f'nominatim-{src}'

    return None, None, None

def main():
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        entries = json.load(f)

    nulls = [e for e in entries if e.get('lat') is None]
    print(f"Total: {len(entries)} desa, perlu geocoding: {len(nulls)}")

    done = still_null = 0

    for entry in entries:
        if entry.get('lat') is not None:
            continue

        done += 1
        label = f"[{done}/{len(nulls)}] {entry['d']}, {entry['kc']}, {entry['kb']}"
        lat, lng, src = get_koordinat(entry['d'], entry['kc'], entry['kb'])

        if lat:
            entry['lat'] = lat
            entry['lng'] = lng
            print(f"{label} -> ({lat}, {lng}) [{src}]")
        else:
            still_null += 1
            print(f"{label} -> TIDAK DITEMUKAN")

        if done % 10 == 0:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
            print(f"  [Checkpoint {done}/{len(nulls)}]")

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    print(f"\nSelesai! Terisi: {done - still_null}, Tidak ditemukan: {still_null}")
    print(f"Selanjutnya: git add {OUTPUT_FILE} && git commit -m 'data: update koordinat kantor desa' && git push")

if __name__ == '__main__':
    main()
