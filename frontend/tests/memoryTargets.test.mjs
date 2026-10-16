import assert from "node:assert/strict";
import test from "node:test";

import {
  extractMemoryTargets,
  unwrapData,
} from "../src/utils/memoryTargets.ts";

const target = { memory_key: "key", claim_id: 7, value: "saved value" };
const expected = { memoryKey: "key", claimId: "7", label: "saved value" };

for (const value of [
  undefined,
  null,
  false,
  true,
  0,
  "",
  "text",
  [],
  [{}],
  { data: null },
]) {
  test(`ignores payload without a memory key: ${String(value)}`, () => {
    assert.deepEqual(extractMemoryTargets(value, "recall"), []);
  });
}

for (const payload of [
  target,
  [target],
  { memories: [target] },
  { claims: [target] },
]) {
  test(`reads supported payload: ${JSON.stringify(payload)}`, () => {
    assert.deepEqual(extractMemoryTargets(payload, "recall"), [expected]);
  });
}

for (const depth of [0, 1, 2, 3, 4]) {
  test(`unwraps at most three data layers: ${depth}`, () => {
    let payload = target;
    for (let index = 0; index < depth; index++) payload = { data: payload };
    assert.strictEqual(
      unwrapData(payload),
      depth <= 3 ? target : payload.data.data.data,
    );
    assert.deepEqual(
      extractMemoryTargets(payload, "recall"),
      depth <= 3 ? [expected] : [],
    );
  });
}

test("arrays stop unwrapping even if they have a data property", () => {
  const payload = [target];
  payload.data = { memory_key: "other" };
  assert.strictEqual(unwrapData(payload), payload);
  assert.deepEqual(extractMemoryTargets(payload, "recall"), [expected]);
});

test("inherited data wrappers remain supported", () => {
  assert.strictEqual(unwrapData(Object.create({ data: target })), target);
});

test("cyclic wrappers stop after three reads", () => {
  let reads = 0;
  const payload = {
    ...target,
    get data() {
      reads++;
      return payload;
    },
  };
  assert.strictEqual(unwrapData(payload), payload);
  assert.equal(reads, 3);
});

test("getter exceptions propagate unchanged", () => {
  const failure = new Error("original failure");
  const payload = {
    get data() {
      throw failure;
    },
  };
  assert.throws(
    () => extractMemoryTargets(payload, "recall"),
    (error) => error === failure,
  );
});

test("memories take precedence over claims, including an empty memories array", () => {
  assert.deepEqual(
    extractMemoryTargets({ memories: [], claims: [target] }, "recall"),
    [],
  );
  assert.deepEqual(
    extractMemoryTargets(
      { memories: [target], claims: [{ memory_key: "other" }] },
      "recall",
    ),
    [expected],
  );
});

test("invalid memories falls back to claims", () => {
  assert.deepEqual(
    extractMemoryTargets({ memories: null, claims: [target] }, "recall"),
    [expected],
  );
});

test("invalid entries are skipped while order and the first duplicate are preserved", () => {
  assert.deepEqual(
    extractMemoryTargets(
      [
        null,
        target,
        { ...target, claim_id: 99, value: "later value" },
        { memory_key: "second", claim_id: 0, value: "second value" },
        "invalid",
        [],
      ],
      "recall",
    ),
    [expected, { memoryKey: "second", claimId: "0", label: "second value" }],
  );
});

test("history clears claim IDs for unique and duplicated keys without changing labels", () => {
  assert.deepEqual(
    extractMemoryTargets(
      [
        target,
        { ...target, claim_id: 99, value: "later" },
        { memory_key: "second", id: 10 },
      ],
      "memory_history",
    ),
    [
      { ...expected, claimId: null },
      { memoryKey: "second", claimId: null, label: "second" },
    ],
  );
});

test("intent comparison remains case sensitive in the parser", () => {
  assert.deepEqual(extractMemoryTargets(target, "MEMORY_HISTORY"), [expected]);
});

test("outer memory key wins and new_claim takes precedence over claim", () => {
  assert.deepEqual(
    extractMemoryTargets(
      {
        memory_key: "outer",
        claim_id: 5,
        value: "outer value",
        new_claim: { memory_key: "new", claim_id: 6, value: "new value" },
        claim: { memory_key: "old", claim_id: 7, value: "old value" },
      },
      "recall",
    ),
    [{ memoryKey: "outer", claimId: "5", label: "new value" }],
  );
});

test("an empty new_claim remains preferred over a populated claim", () => {
  assert.deepEqual(
    extractMemoryTargets({ new_claim: {}, claim: target }, "recall"),
    [],
  );
});

test("a non-record new_claim falls back to claim", () => {
  assert.deepEqual(
    extractMemoryTargets({ new_claim: [], claim: target }, "recall"),
    [expected],
  );
});

for (const [intent, claimId] of [
  ["correct_memory", "9"],
  ["recall", "5"],
]) {
  test(`claim ID precedence for ${intent}`, () => {
    assert.deepEqual(
      extractMemoryTargets(
        {
          memory_key: "key",
          new_claim_id: 9,
          claim_id: 5,
          new_claim: { claim_id: 6, id: 7, value: "nested" },
        },
        intent,
      ),
      [{ memoryKey: "key", claimId, label: "nested" }],
    );
  });
}

test("blank IDs fall back to nested claim_id, then id", () => {
  assert.deepEqual(
    extractMemoryTargets(
      {
        memory_key: "key",
        new_claim_id: " ",
        claim_id: "",
        claim: { claim_id: " 6 ", id: 7 },
      },
      "correct_memory",
    ),
    [{ memoryKey: "key", claimId: " 6 ", label: "key" }],
  );
  assert.deepEqual(
    extractMemoryTargets(
      { claim: { memory_key: "key", claim_id: null, id: 7 } },
      "recall",
    ),
    [{ memoryKey: "key", claimId: "7", label: "key" }],
  );
});

for (const [value, accepted] of [
  [0, true],
  [-1, true],
  [1.5, true],
  [NaN, false],
  [Infinity, false],
  [false, false],
  [null, false],
  ["  ", false],
  [" key ", true],
]) {
  test(`memory keys retain finite numbers and nonblank strings: ${String(value)}`, () => {
    assert.deepEqual(
      extractMemoryTargets({ memory_key: value }, "recall"),
      accepted
        ? [{ memoryKey: String(value), claimId: null, label: String(value) }]
        : [],
    );
  });
}

test("label fallback retains original whitespace and numeric values", () => {
  assert.deepEqual(
    extractMemoryTargets(
      { memory_key: "key", value: " outer ", claim: { value: " " } },
      "recall",
    ),
    [{ memoryKey: "key", claimId: null, label: " outer " }],
  );
  assert.deepEqual(
    extractMemoryTargets(
      { memory_key: "key", value: "outer", claim: { value: 0 } },
      "recall",
    ),
    [{ memoryKey: "key", claimId: null, label: "0" }],
  );
});

test("parsing leaves the original payload and nested claims unchanged", () => {
  const item = Object.freeze({
    ...target,
    new_claim: Object.freeze({ ...target }),
  });
  const payload = Object.freeze({ data: Object.freeze([item]) });
  assert.deepEqual(extractMemoryTargets(payload, "memory_history"), [
    { ...expected, claimId: null },
  ]);
  assert.equal(item.claim_id, 7);
  assert.equal(item.new_claim.claim_id, 7);
});
