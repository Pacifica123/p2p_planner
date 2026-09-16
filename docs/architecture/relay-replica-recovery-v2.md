# Relay replica recovery

An enrolled PC or Android device is a peer. It reads and edits its local board
replica; another personal device is not an acknowledgement service or source of
truth.

For a board already known to a peer, signed encrypted board events and durable
baselines are enough to recover and converge through the configured Nostr
relays. A signed baseline from a newly enrolled node also announces that node's
public key. Trusted nodes retain that workspace-scoped authorization and send
new board metadata, columns, capability and delegation to it as a direct NIP-44
catalog event. The recipient creates the local board shell, then fills it from
the ordinary encrypted board baseline and journal.

The source must reach a relay at least once after creating/importing a board or
making a change. Relay retention and reachability remain transport constraints.
The roaming journal currently converges cards, card order, checklists, card
deletions and board appearance. Comments, labels and later column mutations are
not yet independent multi-writer roaming entities; a catalog carries the
columns that existed when the board was admitted.
