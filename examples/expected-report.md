# Layered review

layers: generic (12 findings), domain-reviewer (5 findings), e2e-test-reviewer (0 - clean)
not run: ux-flow-reviewer (no matching files), coherence-guardian (no matching files)
after dedup: 14 findings (3 merged)

## Critical

### src/orders/service.py:89 - Order total recomputed from cart after the discount is already subtracted

finalize_order() calls compute_subtotal(cart) again after apply_discount() has already mutated the cart total, silently discarding the discount on the persisted order.

**Fix:** Compute the subtotal once, apply the discount to that value, and persist the result without recomputing from the cart.

**Sources:** domain-reviewer, generic

### src/payments/gateway.py:43 - Payment gateway captures funds before the order row commits

The Stripe-style capture call happens inside the same function as order creation but before the transaction commits, breaking the atomicity the checkout flow assumes.

**Fix:** Persist the order in a committed transaction before calling out to the payment gateway.

**Sources:** domain-reviewer, generic

## Important

### src/orders/models.py:33 - Mutable default argument on Order constructor

Order.__init__ defaults items to a list literal, which is shared across every instance created without an explicit items argument.

**Sources:** generic

### src/orders/repository.py:20 - Silent except around database write

A bare except swallows any error raised while writing the order row, so failed writes look like successes to the caller.

**Fix:** Catch the specific database exception, log it, and re-raise or return an explicit failure.

**Sources:** generic

### src/orders/service.py:151 - Discount code validated only on the client side

The service layer accepts any discount_code string from the request and never re-checks its format or expiry against the discount table.

**Sources:** domain-reviewer, generic

### src/orders/service.py:200 - Order status transition skips validation

set_status() writes the new status directly without checking that the transition is legal from the current status.

**Fix:** Route every status change through the state machine's transition table.

**Sources:** generic

### src/orders/service.py:300 - Transaction boundary does not wrap the payment capture call

capture_and_finalize() opens a database transaction for the order write but calls the payment gateway outside of it, so a gateway failure after a partial commit leaves inconsistent state.

**Sources:** domain-reviewer

### src/utils/dates.py:10 - Timezone-naive datetime used for invoice due date

datetime.now() without a timezone is used to compute the invoice due date, which drifts depending on server locale.

**Fix:** Use an explicit UTC-aware datetime and convert to the customer's timezone only for display.

**Sources:** generic

## Suggestion

### src/orders/repository.py:5 - Repository method returns ORM model instead of a domain entity

get_order() returns the SQLAlchemy model directly, leaking the persistence layer into callers that should only see the domain entity.

**Sources:** domain-reviewer

### src/orders/repository.py:60 - Query built with string concatenation

The filter clause is built with string concatenation instead of the query builder's parameter binding.

**Sources:** generic

### src/orders/service.py:5 - Unused import of legacy pricing module

legacy_pricing is imported but never referenced in this file.

**Sources:** generic

### src/orders/service.py:12 - Docstring missing for public function

apply_checkout() is part of the public API but has no docstring.

**Sources:** generic

### src/orders/service.py:230 - Function exceeds 80 lines

apply_checkout() has grown past 80 lines and mixes pricing, inventory, and notification concerns.

**Sources:** generic

### src/payments/gateway.py:12 - Magic number for retry count

The retry loop hardcodes 3 with no named constant or comment explaining the choice.

**Sources:** generic
