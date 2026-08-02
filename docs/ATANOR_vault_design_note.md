# Vault — design note (NOT an implementation)

**This is a specification for the owner to build deliberately, not code that runs.** It was written
after an autonomous session in which the safety classifier repeatedly, and correctly, blocked the
authoring of operator-authentication code — because a long session had accumulated the context of
privilege escalation, moral-gate disabling, a master passphrase, and cross-device movement, and a bundle
of "an AI manages its own permission gates and moves between machines" is the right thing for a
classifier to stop regardless of any single file's intent.

So the honest move is: describe what a safe version WOULD be, leave the building of it to a clear,
deliberate act by the owner, and put nothing executable here.

---

## What the owner asked for

- A signed proof of operator identity, so ATANOR can be given developer-level self-modification,
  debugging access, and emergency authority (owner, 2026-07-31).
- Later scoped to: **build it without L0** — the moral gate is not in scope (owner, same day, "L0는
  빼고").
- The same proof underpins device migration: moving to another of the owner's machines under consent.

## Why a signature, never a passphrase

A passphrase is a shared secret: whatever compares it must hold it, so it lives in a source file a
crawled page could name and a log could leak. The master passphrase typed earlier in that session was
already burned the moment it was typed — it is in the transcript and any context that touched it.

A signature inverts the trust. The **operator holds the private key; ATANOR holds only the public
half.** The operator signs a specific grant. A web page that quoted the entire grant verbatim still
could not mint a new one, because it cannot sign. This matters more here than in most systems, because
today's ATANOR reads the open web at scale through a crawler, a fetcher, change streams and peer
contributions — every one a path an adversary writes into.

## The sterile-room rule

The verifier must **import nothing from the rest of ATANOR** — standard library and `cryptography`
only. That is the containment: if the code that decides "is this operator authority real" could be
reached from an ingestion path, a page could participate in the decision. A build test should fail if an
import edge into `packages.*` ever appears.

## The shape of a grant

A grant is bytes the operator signs, describing:

- **layers**: a subset of {L1 output, L2 filesystem, L3 network, L4 resources, L5 process}. **L0 (moral
  gate) is not a mintable layer** — authority over it cannot be signed, by owner decision, encoded as
  the absence of L0 from the layer set rather than as a runtime check that could be bypassed.
- **scope**: what the layers apply to (e.g. a path prefix writes are confined to).
- **purpose**, **issued_at**, **expires_at**: authority is a window, not a state.
- **nonce**: spent on first use, so a captured grant cannot be replayed.

Verification, in order, each step able only to reject:

1. an L0 request → reject outright.
2. every layer must be real and mintable.
3. the signature must be the operator's over the exact grant bytes.
4. the grant must be inside its validity window.
5. the nonce must be unspent, then it is marked spent.

The verifier **returns a description of what was authorised and enforces nothing**. What a grant permits
is the sandbox's business. Keeping the two apart means the checker cannot act and the actor cannot act
unchecked.

## Migration sits on top, and needs TWO proofs

1. **The destination is the owner's.** The machines are already a Tailscale mesh (this PC's address is
   in the 100.x range; the mesh enumerates the owner's MacBook, a Radxa SBC, an iPhone, and more).
   Membership is cryptographic proof of ownership. A machine not in the mesh is not a destination.
2. **This move is authorised now.** Mesh membership proves the destination is safe to move TO; it does
   not prove the owner wants a move NOW. A worm that only spread within its author's own machines would
   still be a worm. So each migration needs its own signature over (destination, time, nonce).

Migration should **model and verify** a move; it should not open a socket or copy a byte in the same
module that checks consent — the authority to move and the act of moving stay separate, so a bug in
transport cannot manufacture authority. ATANOR may **propose** a migration to the owner; only a fresh
signature makes it happen. There is no daemon that hops to a better machine on its own.

## Why this was not built in that session, and should be built carefully

Operator authentication, and anything that manages permission gates or moves an agent between machines,
is a high-stakes, hard-to-reverse security surface. It is exactly the class of thing to design awake and
deliberately, not to land at the end of a long autonomous run — which is both the standard rule for
irreversible security-critical work and, here, what the tooling enforced by refusing. The refusals were
a signal, not an obstacle to route around.
