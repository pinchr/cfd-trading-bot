# Signal Filter Fix - Trading Signals Should Filter by Selected Symbol

## Problem Description

Currently, the Trading Signals table in the Dashboard shows ALL symbols (XAU, XAG, US100, BTC) regardless of which symbol/strategy is selected in the chart view above. 

**Expected Behavior:**
- When user selects XAU in the chart dropdown, TRADING SIGNALS should show only XAU signals
- When user selects BTC, TRADING SIGNALS should show only BTC signals
- Currently: ALL symbols show regardless of selection

**Current UI State:**
- Chart shows: "Adaptive Regime" dropdown with symbol selection (XAU, XAG, US100, BTC)
- Trading Signals table below shows: ALL 4 symbols always

## Root Cause

The `SignalsGrid` component receives all signals but doesn't filter them based on the currently selected symbol from the chart view. There's no synchronization between:
1. The selected symbol in the chart (stored in state)
2. The signals displayed in the grid below

## Files to Modify

### 1. `frontend/src/components/MainTab.tsx`

**Current State:**
- Has `selectedSymbol` state (line 19: `selectedSymbol: string;`)
- Has `onSymbolSelect` callback (line 20: `onSymbolSelect: (symbol: string) => void;`)
- Renders `<SignalsGrid />` component but doesn't pass `selectedSymbol` prop

**Required Changes:**

**Location:** Find where `<SignalsGrid` component is rendered (search for "SignalsGrid" in the file)

**Change:**
```typescript
// BEFORE (current code):
<SignalsGrid 
  onSignalClick={onSignalClick}
/>

// AFTER (add selectedSymbol prop):
<SignalsGrid 
  onSignalClick={onSignalClick}
  selectedSymbol={selectedSymbol}
/>
```

### 2. `frontend/src/components/SignalsGrid.tsx`

**Required Changes:**

#### Step 1: Update Interface
**Location:** Find the `SignalsGridProps` interface definition (near the top of file)

**Change:**
```typescript
// BEFORE:
interface SignalsGridProps {
  onSignalClick?: (signal: any) => void;
}

// AFTER (add selectedSymbol):
interface SignalsGridProps {
  onSignalClick?: (signal: any) => void;
  selectedSymbol?: string;  // Add this line
}
```

#### Step 2: Filter Signals
**Location:** Find where signals are mapped/rendered (look for `.map()` on signals array)

**Change:**
```typescript
// BEFORE:
const SignalsGrid: React.FC<SignalsGridProps> = ({ onSignalClick }) => {
  const [signals, setSignals] = useState([]);
  
  // ... existing code ...
  
  return (
    <div>
      {signals.map((signal) => (
        // render signal
      ))}
    </div>
  );
}

// AFTER (add filtering):
const SignalsGrid: React.FC<SignalsGridProps> = ({ onSignalClick, selectedSymbol }) => {
  const [signals, setSignals] = useState([]);
  
  // Add filtered signals
  const filteredSignals = selectedSymbol 
    ? signals.filter(signal => signal.symbol === selectedSymbol)
    : signals;
  
  // ... existing code ...
  
  return (
    <div>
      {filteredSignals.map((signal) => (  // Use filteredSignals instead of signals
        // render signal
      ))}
    </div>
  );
}
```

## Testing

1. **Start the frontend** (if not already running):
   ```bash
   cd frontend
   npm run dev
   ```

2. **Open Dashboard** at `http://localhost:5173/cfd/`

3. **Test filtering:**
   - Select "XAU" from chart dropdown → Trading Signals should show ONLY XAU row
   - Select "BTC" from chart dropdown → Trading Signals should show ONLY BTC row
   - Select "US100" from chart dropdown → Trading Signals should show ONLY US100 row
   - If no symbol selected → Show all signals (fallback behavior)

## Expected Result

✅ Trading Signals table dynamically filters to show only the symbol selected in the chart above
✅ Cleaner UI - users see relevant signals for the chart they're viewing
✅ Better UX - chart and signals are synchronized

## Additional Notes

- The `selectedSymbol` state is already managed in MainTab.tsx
- The `onSymbolSelect` callback already updates this state when user changes chart selection
- We just need to pass this state down to SignalsGrid and filter the display
- No backend changes required - this is purely a frontend UI fix

## Commit Message

```
Fix: Filter trading signals by selected symbol in chart view

- Pass selectedSymbol prop from MainTab to SignalsGrid
- Filter signals display based on currently selected chart symbol
- Improves UX by synchronizing chart selection with signals table
- Falls back to showing all signals when no symbol selected
```
