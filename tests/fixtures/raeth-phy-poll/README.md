The complete historical `phy_polling_thread` body is fixed at source commit
`60ae6bf98bd46b68c648620c599f1aa78073131e`. It demonstrates stale EEE state and
publication after failed MDIO reads, using two deterministic inert samples.
It also wrongly forces bidirectional PAUSE when both advertisements contain
neither PAUSE bit (or only ASYM), misses directional asymmetric PAUSE, and
forces PAUSE in half duplex. The same unchanged historical whole body is
executed as the negative control for these cases.

The current native model executes both the complete poller and the actual
Linux4.4 `mii_resolve_flowctrl_fdx` whole inline function. Four advertisement
combinations on each side cover all 16 IEEE 28B-3 pairs in full duplex and
again in half duplex. Independent literal expected MAC bits bind RX to bit5
and TX to bit4 using the actual `mtk_eth_soc.h` definitions; MII advertisement
and flow-control constants are extracted verbatim from the actual UAPI header.
The original 20 sample/failure cases remain, with the half-duplex PAUSE
expectation corrected. Together there are 52 deterministic native scenarios.

The model forces a LEOPARD variant; K2P/MT7621 does not start this poller.
No physical PHY, timing, register ABI or shipping activation is claimed.
