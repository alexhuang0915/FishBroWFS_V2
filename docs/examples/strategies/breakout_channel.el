// Breakout Channel Strategy
// Valid PowerLanguage strategy without Set* syntax

Inputs:
    i_ChannelLen(20),
    i_ATRLen(14),
    i_Multiplier(2.0);

Vars:
    v_HighChannel(0),
    v_LowChannel(0),
    v_ATRVal(0),
    v_MP(0);

v_MP = MarketPosition;

// Calculate channel and ATR
v_HighChannel = Highest(High, i_ChannelLen);
v_LowChannel = Lowest(Low, i_ChannelLen);
v_ATRVal = ATR(i_ATRLen);

// Entry logic - breakout with ATR filter
If v_MP = 0 Then Begin
    If Close > v_HighChannel + v_ATRVal * i_Multiplier Then
        Buy Next Bar at Market;
    If Close < v_LowChannel - v_ATRVal * i_Multiplier Then
        SellShort Next Bar at Market;
End;

// Exit logic - channel reversion
If v_MP > 0 Then Begin
    If Close < v_HighChannel Then
        Sell Next Bar at Market;
End;

If v_MP < 0 Then Begin
    If Close > v_LowChannel Then
        BuyToCover Next Bar at Market;
End;