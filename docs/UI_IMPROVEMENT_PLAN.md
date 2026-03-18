# UI Improvement Plan — CFD Trading Bot Dashboard

**Data utworzenia:** 2026-03-13  
**Branch:** `feature/unified-backtest-fixes-2026-03-11`  
**Status:** Audyt UX (02:30 CET) — Wdrażanie zmian czytelności

---

## 🎯 Cel

Poprawa UX dashboardu głównego, ze szczególnym uwzględnieniem czytelności danych transakcyjnych, stabilności edycji (TP/SL) oraz hierarchii wizualnej informacji.

---

## 🔍 Audit UI & Czytelność (Stan na 02:30)

Widzę, że dashboard przeszedł pewne zmiany [screenshot:2]. Oto analiza aktualnego stanu:

### 1. **Główne Problemy Czytelności (Dashboard)**
- **Wykres (Chart Area):** Candlesticki są bardzo małe i zbite (zbyt dużo świec na ekranie naraz). Wskaźniki techniczne (RSI, MACD) zajmują relatywnie dużo miejsca względem głównej akcji cenowej.
- **Hierarchia Ceny:** Aktualna cena instrumentu na wykresie (`85.39`) jest widoczna, ale dashed line przechodzi przez świece, co wprowadza szum wizualny.
- **Karty Pozycji:** Pasek postępu (Progress Bar) pojawił się pod pozycjami, co jest dobre, ale napisy `SL: 5069.63` i `TP: 5260.60` są ciemnoszare na czarnym tle — **praktycznie nieczytelne** bez przybliżenia.
- **Sidebar:** P&L dzienny i Equity są w tej samej sekcji, ale brakuje separacji wizualnej. "Opened/Closed" trades to tylko liczby bez ikon.

---

## 🛠️ Plan Poprawy Czytelności (Action Items)

### 📈 Wykres i Analiza Techniczna
- [ ] **Density Control:** Zmniejsz liczbę domyślnie wyświetlanych świec o 30% (większe, wyraźniejsze body świec).
- [ ] **Indicator Layout:** Zmień tło paneli RSI/MACD na lekko jaśniejszy szary (`#1a1a1a`), aby oddzielić je od czarnego tła wykresu głównego.
- [ ] **Price Pill:** Dodaj prostokątne tło (pill) pod ceną na osi Y, aby była zawsze czytelna niezależnie od świec w tle.

### 💳 Karty Pozycji (Open Positions)
- [ ] **Contrast Fix:** Zmień kolor czcionki dla SL/TP na biały lub jasnoszary (`#d1d5db`). Aktualny ciemnoszary jest niewidoczny.
- [ ] **Status Badges:** Dodaj małe tagi `PROFIT` (zielony) lub `LOSS` (czerwony) obok numeru ID transakcji.
- [ ] **Progress Bar Polish:** Zmień kolor paska postępu na gradient (Czerwony -> Szary -> Zielony), aby wizualnie pokazać "bezpieczeństwo" pozycji względem SL/TP.

### 🗄️ Sidebar (Kluczowe metryki)
- [ ] **Icons:** Dodaj ikony obok metryk (np. 💰 dla Balance, 📈 dla Win Rate, ⏱️ dla Sessions).
- [ ] **Visual Grouping:** Rozdziel sekcję Balance od sekcji Stats poziomą linią (separator).

---

## 🐛 Krytyczne Fixy Techniczne (Reminder)

### Bug #1: Markery transakcji na lewej krawędzi
**Problem:** Widoczny na [screenshot:2] — strzałki są stłoczone po lewej stronie.
**Fix:** Mapowanie indeksu transakcji musi uwzględniać przesunięcie `bbWarmup`.

### Bug #2: Wskaźniki ucięte/przesunięte
**Problem:** Linie MACD/RSI kończą się przed ostatnią świecą.
**Fix:** Synchronizacja długości tablic wskaźników z `validData.length`.

---

## 🚀 Harmonogram Implementacji

### Faza 1: Quick Wins (Czytelność)
- [ ] Zmiana kontrastu tekstów SL/TP na kartach.
- [ ] Dodanie Price Pill na osi Y.
- [ ] Separatory w sidebarze.

### Faza 2: Techniczne Fixy
- [ ] Naprawa trade markers (pozycja na świecach).
- [ ] Pełna synchronizacja wskaźników na całej szerokości wykresu.

### Faza 3: Nowe Funkcje
- [ ] Margin Level Indicator.
- [ ] Equity Curve (Sparkline).

---

## 🚀 Plan Implementacji

### Faza 1: Fixy techniczne (Piority 🔴)
- [x] Naprawa `idxToX` i synchronizacja indeksów wskaźników/markerów.
- [x] Stabilizacja TP/SL drag (useRef, listener fix).
- [ ] Usunięcie "skakania" linii przy kliknięciu.

### Faza 2: Poprawa Czytelności (Piority 🟡)
- [x] Layout wykresu (wysokość, proporcje paneli).
- [x] Live price label na osi Y.

### Faza 3: Nowy Dashboard UI (Piority 🟢)
- [x] Nowe karty pozycji.
- [x] Progress bary SL/TP.
- [x] Drawdown Alert Box (widoczny gdy DD > 5%).
- [x] Win Rate Donut (wykres kołowy zamiast tekstu).

---

**Ostatnia aktualizacja:** 2026-03-13 02:35 CET

---

### Zmiany zaimplementowane 2026-03-13 02:35:

1. **TP/SL Drag Fix**: 
   - Usunięto stale closure przez przeniesienie logiki do useEffect z refs
   - Inlined handlers żeby uniknąć re-renderów listenerów

2. **Wskaźniki Fix**:
   - Dodano displayRSI, displaySMA20, displaySMA50, displayMACD (sliced wersje)
   - Zaktualizowano rysowanie RSI, SMA, MACD żeby używały sliced wersji

3. **Layout Wykresu**:
   - Zwiększono wysokość wykresu z 320px do 420px
   - Zwiększono RSI panel z 50px do 70px
   - Zwiększono MACD panel z 50px do 60px
   - Zwiększono Volume panel z 45px do 50px

4. **Live Price Badge**:
   - Dodano zielony/czerwony badge na wykresie pokazujący aktualną cenę

5. **Karty Pozycji**:
   - Dodano kolorowy lewy border (zielony dla BUY, czerwony dla SELL)
   - Dodano progress bar wizualizujący odległość ceny od SL i TP
   - Dodano czas trwania pozycji (np. "1h 24m")

6. **Drawdown Alert Box**:
   - Pokazuje się gdy drawdown > 5%
   - Wyświetla procent i kwotę poniżej szczytu

7. **Win Rate Donut**:
   - Zastąpiono tekst wykresem kołowym SVG
   - Kolor zielony dla >=50%, czerwony dla <50%
