The three full function bodies are copied verbatim from source commit
`60ae6bf98bd46b68c648620c599f1aa78073131e`. Their SHA256 values and source
paths are recorded in manifest.json and independently pinned by the harness.
They retain the unsafe mutable callback table and lack reader retirement.

The controlled native baseline starts a real historical control callback,
then invokes the real historical unregister body. It observes unregister
returning before the callback code or a modeled returned-map consumer retires.
No kernel module is actually unloaded, and the model never dereferences
freed code or frees a real provider table.

The current publication helpers and one current control reader execute as
whole source functions. The other 30 caller bodies are bound to the actual
whole-function cleanup scopes; they are not all executed in the native model.
Linux RCU/SRCU/workqueue operations are inert pthread/counter backends.
The actual Linux4.4 source for synchronize/process/reschedule is separately
bound as a source-only reference; static SRCU uses no runtime allocator.

Provider ABI and required contract:

- `VOID wifi_fwd_register(struct wifi_fwd_func_table *table)` and
  `VOID wifi_fwd_unregister(VOID)` retain their signatures and table layout.
- Writers must run in sleepable context, outside these callback/read scopes,
  and without a lock required by an existing reader.
- A provider must unregister before freeing its code or callback-owned data;
  unregister waits for existing atomic RCU and process SRCU consumers.
- A provider remains responsible for its own asynchronous work and reference
  lifetimes. This does not support a module that unloads without unregister.
- Unsupported non-GPL or CONFIG_SRCU-disabled builds receive an explicit
  compilation diagnostic rather than an unsafe fallback or license change.

The configured K2P tree has no forwarding provider implementation. This is
an API lifetime regression, not a claim of an observed shipping-provider
failure, real packet-path throughput, PCI removal or hardware validation.
