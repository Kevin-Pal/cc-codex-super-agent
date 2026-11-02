# Synthetic project

This example contains no real project data. Follow the shared framework rules when installed, and keep this example's task within its own directory.

A sample task is to prepare `notes.md` with three facts derived only from the synthetic input below: apples=3, pears=2, total fruit=5. Do not fetch external data or change other projects.

Accept only after reading back the produced file and checking the three values. The Router may request one correction in the same Worker thread. Human input changing pears to 4 requires a fresh total of 7 and synchronization before another automatic turn.
