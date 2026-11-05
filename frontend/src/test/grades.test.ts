import { parseScore } from "@/lib/grades";

test.each([
  ["10", { kind: "value", value: 10 }],
  ["10.0", { kind: "value", value: 10 }],
  ["8.", { kind: "value", value: 8 }],
  [" 8,5 ", { kind: "value", value: 8.5 }],
  ["8,55", { kind: "value", value: 8.55 }], // one decimal is the server's rule, per cell
  ["0", { kind: "value", value: 0 }],
  [",5", { kind: "invalid" }],
  ["abc", { kind: "invalid" }],
  ["8,5,5", { kind: "invalid" }],
  ["-1", { kind: "invalid" }],
  ["", { kind: "clear" }],
  ["   ", { kind: "clear" }],
])("parseScore(%j) is %j", (text, parsed) => {
  expect(parseScore(text)).toEqual(parsed);
});
