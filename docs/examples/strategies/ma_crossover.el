// Simple Moving Average Crossover Strategy
// Valid PowerLanguage strategy without Set* syntax

Inputs:
    i_FastMA(10),
    i_SlowMA(20),
    i_RiskPct(1.0);

Vars:
    v_Fast(0),
    v_Slow(0),
    v_MP(0);

v_MP = MarketPosition;

// Calculate moving averages
v_Fast = Average(Close, i_FastMA);
v_Slow = Average(Close, i_SlowMA);

// Entry logic
If v_MP = 0 Then Begin
    If v_Fast > v_Slow Then
        Buy Next Bar at Market;
    If v_Fast < v_Slow Then
        SellShort Next Bar at Market;
End;

// Exit logic
If v_MP > 0 Then Begin
    If v_Fast < v_Slow Then
        Sell Next Bar at Market;
End;

If v_MP < 0 Then Begin
    If v_Fast > v_Slow Then
        BuyToCover Next Bar at Market;
End;