// RSI Mean Reversion Strategy
// Valid PowerLanguage strategy without Set* syntax

Inputs:
    i_RSILen(14),
    i_Overbought(70),
    i_Oversold(30);

Vars:
    v_RSI(0),
    v_MP(0);

v_MP = MarketPosition;

// Calculate RSI
v_RSI = RSI(Close, i_RSILen);

// Entry logic - mean reversion
If v_MP = 0 Then Begin
    If v_RSI > i_Overbought Then
        SellShort Next Bar at Market;
    If v_RSI < i_Oversold Then
        Buy Next Bar at Market;
End;

// Exit logic - RSI returns to middle
If v_MP > 0 Then Begin
    If v_RSI > 50 Then
        Sell Next Bar at Market;
End;

If v_MP < 0 Then Begin
    If v_RSI < 50 Then
        BuyToCover Next Bar at Market;
End;