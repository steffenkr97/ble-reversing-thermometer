mega – danke fürs Log! Ich geh’s **zeile für zeile** (bzw. Block für Block) durch und erkläre, was da genau passiert. Danach hast du ein klares Bild, was nRF Connect dir zeigt und welche UUIDs wichtig sind.

---

# 1) Scan-Phase (Werbung/Advertising des Geräts)

```
[07:00:40.2380] Normal: Scanner On.
[07:00:40.6680] Normal: Device Scanned.
[07:00:40.6700] Normal: -29 dBm
[07:00:40.6700] Normal: 430.73 ms
...
[07:01:04.3850] Normal: -21 dBm
[07:01:04.3850] Normal: 3389.21 ms
```

**Bedeutung:**

* **Scanner On / Device Scanned** → nRF Connect hat dein Thermometer im **Advertising** gefunden.
* Die Zeilen mit **„-29 dBm“, „-30 dBm“, ...** zeigen die **RSSI** (Signalstärke). −20 dBm ≈ sehr nah; −80 dBm ≈ weit weg.
* Die Zeilen **„430.73 ms“, „845.36 ms“, ...** sind der **gemessene Abstand** zwischen empfangenen Werbepaketen – effektiv das **Advertising-Intervall** (bzw. das Zeitdelta bis zum nächsten gesehenen Packet). Werte um ~**840 ms** deuten auf ~1 s Werbeintervall (plus Jitter). Größere Deltas wie **1695 / 2541 / 3389 ms** sind schlicht ausgelassene Sichtungen (Funkkollisionen, Kanalwechsel, Sleep, etc.).

**Takeaway:** Gerät sendet regelmäßig Werbepakete, gute Nähe (−20 bis −30 dBm).

---

# 2) Verbindungsaufbau & Service-Discovery

```
[07:01:05.2940] Normal: Connected.
[07:01:05.6490] Normal: Discovered Device Information and FFE0 Services.
```

**Bedeutung:**

* **Connected.** → GATT-Verbindung steht.
* Es wurden zwei Services gefunden:

  * **Device Information Service (DIS)** → Standardservice mit Geräteinfos.
  * **FFE0** → **Custom-Service** (häufig bei China-Geräten), volle UUID meist `0000FFE0-0000-1000-8000-00805f9b34fb`.

---

# 3) Device Information Service – Standard-Characteristics

```
[07:01:05.8320] Normal: Discovered System ID, Model Number String, Serial Number String,
Firmware Revision String, Hardware Revision String, Software Revision String,
Manufacturer Name String, IEEE 11073-20601 Regulatory Certification Data List, and PnP ID
Characteristics for Service Device Information.
```

**Bedeutung:** Im **DIS** liegen diese standardisierten Characteristics (mit 16-Bit UUIDs):

* **2A23** System ID
* **2A24** Model Number String
* **2A25** Serial Number String
* **2A26** Firmware Revision String
* **2A27** Hardware Revision String
* **2A28** Software Revision String
* **2A29** Manufacturer Name String
* **2A2A** IEEE 11073…
* **2A50** PnP ID

Das sind Info-Strings, **keine Messwerte**.

---

# 4) Custom-Service FFE0 → die spannenden Chars

```
[07:01:05.9480] Normal: Discovered FFF5 and FFF3 Characteristics for Service FFE0.
[07:01:06.0070] Normal: FFF5 has no Descriptors.
[07:01:06.1290] Normal: Discovered Client Characteristic Configuration Descriptors for Characteristic FFF3
```

**Bedeutung:**

* Im **FFE0-Service** gibt es mindestens zwei Characteristics:

  * **FFF3** → hat einen **CCCD** (Client Characteristic Configuration Descriptor). Das bedeutet: **Notifications/Indications** sind möglich (genau das wollen wir zum Mitlauschen!).
  * **FFF5** → **ohne** Deskriptoren (typisch für eine **Write/Control-Char**, mit der man z. B. „Start Sync“ anstößt).
* Typische Rollen in solchen Designs:

  * **FFF5**: App sendet *Befehle* (Write/Write Without Response), z. B. „gib aktuelle Anzeige“, „schicke Logs“.
  * **FFF3**: Gerät **streamt Daten** (Notify) als Antwort auf den Befehl.

**Takeaway:** **FFF3** ist unser Hauptkandidat für **Messdaten (Notify)**. **FFF5** ist sehr wahrscheinlich die **Steuer-Characteristic (Write)**, die die App beim „Tippen für Logs“ nutzt.

---

# 5) Konkrete Reads/Updates aus dem DIS

```
[07:02:17.2120] Normal: Updated Value of Characteristic 2A23 to D900 0000 0000 DBF4.
[07:02:17.2120] Application: "D900 0000 0000 DBF4" value received.
```

**Bedeutung:**

* **2A23 (System ID)** wurde gelesen. 8-Byte-Feld: `D9 00 00 00 00 00 DB F4`
  Nach Spezifikation ist das meist: **Manufacturer Identifier** (5 Bytes) + **Organizationally Unique Identifier (OUI)** (3 Bytes).
  → Hier wäre **OUI** wahrscheinlich `00:DB:F4`. (Man *kann* das später gegen OUI-Listen gegenprüfen; für’s Reverse Engineering ist das meist nur „nice to have“.)

```
[07:02:52.8530] Normal: Updated Value of Characteristic 2A24 to 4D6F 6465 6C20 4E75 6D62 6572.
[07:02:52.8530] Application: "Model Number" value received.
```

**Bedeutung:**

* **2A24 (Model Number String)** → Hex `4D 6F 64 65 6C 20 4E 75 6D 62 65 72` = ASCII **„Model Number“** (scheint generisch/Platzhalter).

```
[07:03:09.0530] Normal: Updated Value of Characteristic 2A29 to 4D61 6E75 6661 6374 7572 6572 204E 616D 65.
[07:03:09.0530] Application: "Manufacturer Name" value received.
```

**Bedeutung:**

* **2A29 (Manufacturer Name String)** → Hex decodiert zu **„Manufacturer Name“** (wieder generisch).
  → Viele Billiggeräte füllen DIS-Strings nur minimal aus.

**Wichtig:** Diese drei „Updated Value“-Zeilen sind **reine Geräte-Infos**. **Noch keine Temperaturdaten.**
Die **Temperatur/Logs** erwarten wir auf **FFF3 (Notify)**, *nachdem* die App über **FFF5 (Write)** „Sync“ anstößt.

---

# 6) Was heißt das für dein Reverse-Engineering?

* Du hast jetzt das grobe **Protokollgerüst**:

  * **Service**: `FFE0`
  * **Control-Char** (vermutlich): `FFF5` (Write / ggf. „Start“)
  * **Data-Char**: `FFF3` (**Notify**) → hier sollten die **Messwerte/Logs** als **RAW-Bytes** eintrudeln.
* Das deckt sich mit vielen günstigen BLE-Thermometern: „FFF5 start → FFF3 notify“.

---

# 7) Wie wir damit weitermachen (sehr konkret)

1. **Auf dem Mac** mit meinem Listener auf **Notify (FFF3)** lauschen und **gleichzeitig** in der Hersteller-App den **Sync antippen**.

   * Wenn Daten kommen → wir dekodieren die **RAW-Bytes** (Offset/Skalierung/Checksum).
2. **Wenn nichts kommt**:

   * Sehr wahrscheinlich verlangt das Gerät vorab einen **Write** auf **FFF5** (z. B. `0x01` als „Start Sync“).
   * Dann schicken wir per Skript einen Test-Write auf **FFF5** und aktivieren **FFF3-Notify**.

Wenn du willst, passe ich dir jetzt sofort das Python-Skript so an, dass es:

* **explizit FFF3** als Notify **abonniert** und
* **optional** einen **konfigurierbaren Write** an **FFF5** sendet (z. B. `--kick 0x01`), **bevor** es lauscht.

---

# 8) Kurze Checkliste zum Log (damit du’s „fühlst“)

* `Scanner On / Device Scanned` → Advertising sichtbar (Gerät „blinkt“ in die Welt).
* `-29 dBm / 845 ms` → starkes Signal, ~1 s Werbeintervall.
* `Connected` → GATT-Session steht.
* `Discovered Device Information and FFE0 Services` → Standard-Infos + **Custom-Service** vorhanden.
* `FFF3 hat CCCD` → **Notify möglich** → **Datenkanal**.
* `2A23/2A24/2A29 updated` → nur **Info-Strings** (kein Messstream).

---

Wenn du mir noch **eine** der folgenden Infos gibst, schreibe ich dir sofort das passende **Skript v2**:

* Bestätigung aus nRF Connect, dass **FFF3** die Eigenschaft **Notify** hat (steht meist direkt dabei), und ob **FFF5** **Write** / **Write Without Response** hat.
* Oder du startest mein vorheriges `ble_capture_fff3.py` und postest 3–5 Zeilen `RAW=...`, die während des App-Syncs erscheinen.

Dann baue ich dir:

* einen **gezielten FFF3-Listener**,
* optional **Kick-Write** auf FFF5,
* und gleich den **Parser** (°C als Zahl) + CSV/MQTT/Influx-Option.

