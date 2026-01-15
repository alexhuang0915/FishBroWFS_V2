// INVALID Strategy with SetStopLoss
// This should be rejected by the generator

Inputs:
    i_Len(20);

Vars:
    v_MA(0);

v_MA = Average(Close, i_Len);

If MarketPosition = 0 Then Begin
    If Close > v_MA Then
        Buy Next Bar at Market;
End;

// FORBIDDEN: Set* syntax
SetStopLoss(100);
SetProfitTarget(200);