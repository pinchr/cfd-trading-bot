# ALGORYTM SCORINGU I SIGNALU - DOKUMENTACJA SZCZEGÓŁOWA

**Wersja:** 1.0  
**Data:** 2026-03-11  
**Cel:** Dokumentacja dla konsultacji ze specjalistami

---

## 1. ARCHITEKTURA SYSTEMU

### 1.1 Pliki Źródłowe
- `/backend/strategy/strategy.py` - ScoreEngine, compute_score(), get_signal()
- `/backend/strategy/indicators.py` - Indicator, normalized_value()
- `/backend/services/strategy_manager.py` - analyze_with_new_strategy()
- `/backend/strategy/strategies.json` - Konfiguracja strategii

### 1.2 Przepływ Danych
```
CANDLE DATA → INDICATORS → SCORE_ENGINE → SIGNAL → BACKEND → FRONTEND
```

---

## 2. ALGORYTM KROK PO KROKU

### KROK 1: Pobranie Danych Świecowych
```python
candles = get_cached_candles(symbol, timeframe, 100)
# Pobiera 100 ostatnich świec
```

### KROK 2: Obliczenie Wskaźników Technicznych
```python
indicators = TechnicalIndicators.calculate_all(candles, period=14)
# Zwraca słownik:
# {
#   'RSI': 65.0,
#   'MACD': {'histogram': -5.2, 'macd_line': 10.0, 'signal_line': 15.2},
#   'MOMENTUM': 2.5,
#   'ADX': 28.0,
#   ...
# }
```

### KROK 3: Inicjalizacja Wskaźników Strategii
```python
# Dla każdego wskaźnika w strategii tworzony jest obiekt Indicator
for ind_config in strategy.score_indicators:
    name = ind_config['name']  # np. 'RSI'
    indicator = create_indicator(name, period=14)
    # Indicator przechowuje historię wartości
```

### KROK 4: Normalizacja Wartości Wskaźników

**Metoda:** `Indicator.normalized_value(range_min, range_max)`

```python
def normalized_value(self, range_min=-1.0, range_max=1.0):
    # 1. Pobierz surową wartość
    val = self.value()  # np. RSI = 65
    
    # 2. Pobierz zakres z danych historycznych
    min_val, max_val = self._get_range()  # np. RSI: (30, 70)
    
    # 3. Oblicz midpoint jako punkt neutralny
    mid = (min_val + max_val) / 2  # np. 50
    half_range = (max_val - min_val) / 2  # np. 20
    
    # 4. Znormalizuj do [-1, 1]
    if half_range > 0:
        normalized = (val - mid) / half_range
    else:
        normalized = 0.0
    
    # 5. Przeskaluj do żądanego zakresu
    scaled = normalized * ((range_max - range_min) / 2)
    
    return scaled
```

**PROBLEM 1: Dynamiczny Zakres**
- Zakresy są obliczane z danych historycznych (np. min=30, max=70 dla RSI)
- W różnych okresach zakresy się zmieniają!
- To powoduje NIESTABILNOŚĆ normalizacji

**PROBLEM 2: Zakres dla każdego wskaźnika**

| Wskaźnik | Typowy Zakres | Problem |
|----------|---------------|---------|
| RSI | 0-100 | Stabilny |
| MACD histogram | -100 do +100 | ZALEŻNY OD VOLATILITY! |
| MOMENTUM | -10 do +10 | ZALEŻNY OD SKALI! |
| ADX | 0-100 | Stabilny |

### KROK 5: Obliczenie Score (ScoreEngine.compute_score)

```python
def compute_score(self) -> float:
    total_score = 0.0
    total_weight = 0.0
    
    for ind_config in self.score_indicators:
        name = ind_config.get('name', '').upper()  # np. 'RSI'
        weight = ind_config.get('weight', 0.0)      # np. 1.2
        normalized_range = ind_config.get('normalized_range', [-1, 1])
        
        # Pobierz wskaźnik
        indicator = self.indicators[name]
        
        # Znormalizuj do [-1, 1]
        normalized = indicator.normalized_value(-1, 1)
        
        # Dodaj ważony wkład
        total_score += normalized * weight
        total_weight += weight
    
    # Normalizuj przez sumę wag
    if total_weight > 0:
        total_score = total_score / total_weight
    
    return total_score
```

**PRZYKŁAD OBLICZENIA:**

Dla strategii `xau_v2_momentum`:
```json
{
  "indicators": [
    {"name": "RSI", "weight": 1.2},
    {"name": "MACD", "weight": 0.0},
    {"name": "MOMENTUM", "weight": 1.2}
  ]
}
```

Scenariusz:
- RSI = 65 (zakres: 30-70) → normalized = (65-50)/20 = 0.75
- MOMENTUM = 3.5 (zakres: -5 do 5) → normalized = (3.5-0)/5 = 0.70

Obliczenie:
```
total_score = (0.75 * 1.2) + (0.70 * 1.2) = 0.9 + 0.84 = 1.74
total_weight = 1.2 + 1.2 = 2.4

score = 1.74 / 2.4 = 0.725
```

### KROK 6: Generowanie Sygnału (get_signal)

```python
def get_signal(self) -> Optional[str]:
    min_score = self.config.get('min_score', 0.3)  # Próg minimalny
    
    score = self.compute_score()
    
    if score >= min_score:
        return 'buy'
    elif score <= -min_score:
        return 'sell'
    
    return None  # neutral
```

**min_score = 0.3 (30%)** - próg minimalny

**PRZYKŁAD:**
- score = 0.725
- min_score = 0.3
- 0.725 >= 0.3 → **BUY**

### KROK 7: Konwersja do Formatu Wyjściowego

W `strategy_manager.py`:

```python
# Clampowanie do [-2, 2]
raw_clamped = max(-2.0, min(2.0, score))

# Mapowanie do [0, 1]
abs_score = abs(raw_clamped) / 2.0

# Minimum confidence
confidence = min(1.0, abs_score)
if confidence < 0.15:
    confidence = 0.15

# Score końcowy = kierunek * confidence
normalized_score = direction * confidence
```

---

## 3. KONFIGURACJA STRATEGII

### 3.1 Struktura strategii (strategies.json)

```json
{
  "id": "xau_v2_momentum",
  "name": "XAU v2 Momentum",
  "symbol": "XAU",
  "timeframe": "5m",
  "trade_direction": "long_only",
  "score": {
    "min_score": 0.3,
    "direction_mode": "score_only",
    "indicators": [
      {
        "name": "RSI",
        "weight": 1.2,
        "normalized_range": [-1, 1]
      },
      {
        "name": "MACD",
        "weight": 0.0,
        "normalized_range": [-1, 1]
      },
      {
        "name": "MOMENTUM",
        "weight": 1.2,
        "normalized_range": [-1, 1]
      }
    ]
  },
  "filters": {...},
  "exits": {...},
  "risk": {...}
}
```

### 3.2 Parametry Score

| Parametr | Wartość | Znaczenie |
|----------|---------|-----------|
| min_score | 0.3 | Minimalny próg dla sygnału |
| direction_mode | score_only | Tryb generowania kierunku |
| weight | 1.2 | Waga wskaźnika |

---

## 4. WĄTLIWOŚCI I PROBLEMY

### 4.1 Zidentyfikowane Problemy

| # | Problem | Severity | Opis |
|---|---------|----------|------|
| 1 | Dynamiczny zakres normalizacji | 🔴 Krytyczny | Zakresy obliczane z danych historycznych, niestabilne |
| 2 | MACD histogram bez limitów | 🔴 Krytyczny | Może mieć wartości -1000 do +1000 |
| 3 | min_score = 0.3 może być za niski | 🟡 Średni | Próg 30% może generować za dużo sygnałów |
| 4 | Brak stałych zakresów | 🟡 Średni | Każdy wskaźnik powinien mieć stały zakres |

### 4.2 Propozycje Rozwiązań

**DLA PROBLEMU 1 i 2 - Stałe Zakresy:**
```python
INDICATOR_RANGES = {
    'RSI': {'min': 0, 'max': 100},
    'MACD': {'min': -10, 'max': 10},  # histogram
    'MOMENTUM': {'min': -5, 'max': 5},
    'ADX': {'min': 0, 'max': 100},
}
```

**DLA PROBLEMU 3 - Większy min_score:**
```json
"min_score": 0.5  // 50% - bardziej restrykcyjny
```

---

## 5. PRZYPADKI TESTOWE

### 5.1 Przypadek 1: Silny BUY
```
RSI = 25 (oversold) → normalized = -1.0
MOMENTUM = -4 (negative) → normalized = -0.8
weight = 1.2 każdy

score = (-1.0 * 1.2 + -0.8 * 1.2) / 2.4 = -2.16 / 2.4 = -0.9
min_score = 0.3
-0.9 <= -0.3 → SELL ✓
```

### 5.2 Przypadek 2: Słaby BUY
```
RSI = 42 (near oversold) → normalized = -0.4
MOMENTUM = 0.5 (neutral) → normalized = 0.05
weight = 1.2 każdy

score = (-0.4 * 1.2 + 0.05 * 1.2) / 2.4 = -0.42 / 2.4 = -0.175
min_score = 0.3
-0.175 > -0.3 → NEUTRAL ✓
```

### 5.3 Przypadek 3: Neutral
```
RSI = 50 (neutral) → normalized = 0.0
MOMENTUM = 0 (neutral) → normalized = 0.0

score = 0.0
0.0 < 0.3 i > -0.3 → NEUTRAL ✓
```

---

## 6. PYTANIA DO SPECJALISTÓW

1. **Czy normalizacja oparta na danych historycznych jest poprawna?**
   - Czy lepsze byłyby stałe zakresy?

2. **Jakie powinny być stałe zakresy dla MACD histogram?**
   - Obecnie: zależne od volatility
   - Propozycja: -10 do +10

3. **Czy min_score = 0.3 jest odpowiedni?**
   - Czy powinno być wyższe (0.5)?

4. **Czy wagi 1.2 są optymalne?**
   - Czy powinny być wyższe/niższe?

5. **Czy tryb score_only jest najlepszy?**
   - Alternatywa: rsi_momentum

---

## 7. WALIDACJA

Po zmianach warto przetestować:
- Czy score mieści się w [-1, 1]?
- Czy min_score skutecznie filtruje słabe sygnały?
- Czy różne symbole dają różne wyniki?
- Czy rynek niedźwiedzi daje SELL, a byczy daje BUY?

