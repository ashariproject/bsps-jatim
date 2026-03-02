---
description: Mengisi koordinat lat/lng pada file JSON desa dengan mencari lokasi Kantor Kepala Desa/Balai Desa menggunakan Nominatim (OpenStreetMap)
---

# Skill: Geocoding Kantor Desa

Skill ini digunakan untuk mengisi koordinat `lat`/`lng` yang masih `null` di dalam file JSON desa BSPS, dengan cara mencari **Kantor Kepala Desa / Kantor Desa / Balai Desa** yang paling akurat menggunakan Nominatim (OpenStreetMap) dan Overpass API.

## Kondisi Penggunaan

Gunakan skill ini saat:
- File JSON desa (misal `data_desa_t2.json`) memiliki entri dengan `lat: null` atau `lng: null`
- Perlu koordinat yang akurat (titik kantor desa, bukan titik tengah wilayah)

## Format Data JSON yang Didukung

```json
[
  { "k": "3502011006", "d": "DONOROJO", "kc": "NAWANGAN", "kb": "KAB. PACITAN", "j": 10, "lat": null, "lng": null }
]
```

## Script Geocoding

Buat file `geocode_kantordesa.py` di folder proyek dengan isi berikut:

```python
"""
geocode_kantordesa.py
Mengisi lat/lng null di JSON desa dengan mencari:
  1. Kantor Kepala Desa / Kantor Desa / Balai Desa via Overpass API (OSM)
  2. Fallback: Nominatim search "Desa X, Kecamatan Y, Kabupaten Z"
  3. Fallback: Nominatim search nama kecamatan saja (perkiraan lokasi)
"""
import json, time, urllib.request, urllib.parse, os

INPUT_FILE  = 'data_desa_t2.json'   # ganti jika file berbeda
OUTPUT_FILE = 'data_desa_t2.json'
DELAY       = 1.2   # jeda antar request (Nominatim: max 1 req/detik)
HEADERS     = {'User-Agent': 'BSPS-Dashboard-Geocoder/2.0 (bsps-jatim2026.my.id)'}

# Bounding box Jawa Timur untuk membatasi pencarian
JATIM_BBOX = "viewbox=110.8,-8.9,114.9,-6.8&bounded=1"

def overpass_kantordesa(desa, kec, kab):
    """Cari Kantor Desa via Overpass API (OSM amenity/office)"""
    kab_clean = kab.replace('KAB. ', '').replace('KOTA ', '').title()
    kec_clean = kec.title()
    desa_clean = desa.title()
    
    # Query Overpass: cari node/way dengan tag amenity/office yang namanya mengandung nama desa
    query = f"""
[out:json][timeout:10];
area["name"="Jawa Timur"]["admin_level"="4"]->.jatim;
(
  node(area.jatim)["amenity"="townhall"]["name"~"{desa_clean}",i];
  node(area.jatim)["office"="government"]["name"~"(Kantor|Balai).*(Desa|Kepala).*{desa_clean}",i];
  node(area.jatim)["office"="government"]["name"~"{desa_clean}",i];
);
out center 1;
"""
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
    except Exception as e:
        pass
    return None, None, None

def nominatim_search(query):
    """Cari koordinat via Nominatim"""
    try:
        params = urllib.parse.urlencode({
            'q': query,
            'format': 'json',
            'limit': 1,
            'countrycodes': 'id',
            'viewbox': '110.8,-8.9,114.9,-6.8',
            'bounded': 1
        })
        url = f"https://nominatim.openstreetmap.org/search?{params}"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        if data:
            return round(float(data[0]['lat']), 6), round(float(data[0]['lon']), 6)
    except:
        pass
    return None, None

def get_koordinat(desa, kec, kab):
    """
    Urutan pencarian:
    1. Overpass: Kantor/Balai Desa (paling akurat)
    2. Nominatim: "Kantor Desa X, Kecamatan Y"
    3. Nominatim: "Kantor Kepala Desa X"
    4. Nominatim: "Desa X, Kecamatan Y, Kabupaten Z"
    5. Nominatim: "Kecamatan Y, Kabupaten Z" (fallback kasar)
    """
    kab_clean = kab.replace('KAB. ', '').replace('KOTA ', '').title()
    kec_clean = kec.title()
    desa_clean = desa.title()

    # 1. Overpass (Kantor Desa via OSM tags)
    lat, lng, src = overpass_kantordesa(desa, kec, kab)
    time.sleep(DELAY)
    if lat: return lat, lng, src

    # 2. Nominatim: Kantor Desa spesifik
    queries = [
        f"Kantor Desa {desa_clean}, Kecamatan {kec_clean}, {kab_clean}, Jawa Timur",
        f"Balai Desa {desa_clean}, {kec_clean}, {kab_clean}, Jawa Timur",
        f"Kantor Kepala Desa {desa_clean}, {kab_clean}",
        f"Desa {desa_clean}, Kecamatan {kec_clean}, Kabupaten {kab_clean}, Jawa Timur",
        f"{desa_clean}, {kec_clean}, {kab_clean}, Jawa Timur, Indonesia",
        f"Kecamatan {kec_clean}, Kabupaten {kab_clean}, Jawa Timur",  # fallback kecamatan
    ]

    for i, q in enumerate(queries):
        lat, lng = nominatim_search(q)
        time.sleep(DELAY)
        if lat:
            src = 'nominatim-kantordesa' if i < 3 else 'nominatim-desa' if i < 5 else 'nominatim-kecamatan'
            return lat, lng, src

    return None, None, None

def main():
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        entries = json.load(f)

    nulls = [e for e in entries if e.get('lat') is None]
    print(f"Total entri: {len(entries)}, perlu geocoding: {len(nulls)}")

    done = 0
    still_null = 0

    for entry in entries:
        if entry.get('lat') is not None:
            continue

        done += 1
        label = f"[{done}/{len(nulls)}] {entry['d']}, {entry['kc']}, {entry['kb']}"
        lat, lng, src = get_koordinat(entry['d'], entry['kc'], entry['kb'])

        if lat:
            entry['lat'] = lat
            entry['lng'] = lng
            print(f"{label} -> OK ({lat}, {lng}) [{src}]")
        else:
            still_null += 1
            print(f"{label} -> TIDAK DITEMUKAN")

        # Checkpoint setiap 10 entri
        if done % 10 == 0:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
            print(f"  [Checkpoint {done}/{len(nulls)}]")

    # Simpan final
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    print(f"\nSelesai! Terisi: {done - still_null}, Tidak ditemukan: {still_null}")
    print(f"Hasil disimpan ke {OUTPUT_FILE}")

if __name__ == '__main__':
    main()
```

## Cara Menggunakan

1. Pastikan file JSON desa sudah ada di folder yang sama
2. Edit variabel `INPUT_FILE` dan `OUTPUT_FILE` jika nama file berbeda
3. Jalankan:
   ```
   python geocode_kantordesa.py
   ```
4. Script akan membuat checkpoint otomatis setiap 10 entri — aman jika diinterupsi
5. Setelah selesai, push hasilnya ke GitHub:
   ```
   git add data_desa_t2.json; git commit -m "data: Update koordinat kantor desa Tahap II"; git push
   ```

## Catatan

- **Rate limit**: Nominatim max 1 request/detik — jangan ubah `DELAY` menjadi lebih kecil dari 1.0
- **Akurasi sumber (urutan terbaik ke terburuk)**:
  1. `overpass` — titik Kantor/Balai Desa dari OSM (paling akurat)
  2. `nominatim-kantordesa` — koordinat kantor desa dari Nominatim
  3. `nominatim-desa` — koordinat wilayah desa
  4. `nominatim-kecamatan` — koordinat kecamatan (perkiraan, kurang akurat)
- Desa yang masih `null` setelah dijalankan bisa diisi manual di file JSON
