from dgkit import hbar_chart
print(hbar_chart("perf_real", ["Real model, 50 chats,\nworker 50 threads (cold)", "Real model, 50 chats,\nworker 50 threads (warm)", "Real model, one idle chat",
    "Real model, 16 threads\n(before the fix)", "Real model, no warm-up\n(before the fix)"], [5.77, 5.92, 4.0, 14.7, 10.0],
    "90th percentile reply time, real gpt-4o-mini", "seconds, message received to reply accepted", limit=8, limit_label="NFR-01: 8 s"))
print(hbar_chart("perf_mock", ["Mock model, 1 message at a time\n(50 chats)", "Mock model, 16 threads\n(50 chats)", "Mock model, 50 threads\n(50 chats)",
    "Mock model, 50 threads\n(100 chats)"], [42.8, 2.0, 2.8, 8.5], "90th percentile reply time, offline mock model", "seconds, message received to reply accepted", limit=8, limit_label="8 s"))
