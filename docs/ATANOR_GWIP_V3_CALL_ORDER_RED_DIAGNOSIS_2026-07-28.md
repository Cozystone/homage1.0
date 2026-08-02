# GWIP v3 call-order RED diagnosis

## Scope and evidence boundary

This diagnosis reopens only the evaluator interpretation of the immutable
GWIP capability v1 and v3 evidence. It does not alter or reinterpret either
sealed verdict, and it does not run another empirical attempt.

- Frozen candidate:
  `51de7aadf188f9889ff1ea051012693e5aa529e2`
- v1 evaluator:
  `6346519eab4fcb7e9bc841ee860abc9d9068a541`
- v1 raw evidence SHA-256:
  `0612a080e549918eabfe8f453abba1f8176daf48b5cddd9cff2ff50f02a429c3`
- v1 receipt checksum:
  `5677e18f9ea900253d0aeabb0c62d4b5a2985d90a27a998402e924b23b2a2cd5`
- v3 evaluator:
  `9c751107407f8238d39d6eaed7320523a895a358`
- v3 raw evidence SHA-256:
  `dcaf8141dff574ec28bab6a18da1829fad47f0bd9a2ca45c3bff2dc2bce34202`
- v3 receipt checksum:
  `e86a97ae9fad9fb4293882186826f5299cd01e5035e132f307215b0c5be6004e`
- Both historical verdicts remain `CAPABILITY_RED`.

The raw evidence, authority shards, parent-owned protocol, candidate trace,
and evaluator source were compared independently. No package under
`packages/` was changed.

## Exact ordinal census

Let `U = {0, 1, ..., 1023}`. Ordinals below are numerically sorted. The digest
is SHA-256 of the comma-separated decimal ordinal list without spaces.

### v1 failed ordinals

Count: 627. Digest:
`9318a0ed6bb077a1100bf64a5bae876d3f422087a365019fbafef96cf86b773c`.

```
0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119,120,121,122,123,124,125,126,127,128,129,130,131,132,133,134,135,136,137,138,139,140,141,142,143,144,145,146,147,148,149,150,151,152,153,154,155,156,157,158,159,160,161,162,163,164,165,166,167,168,169,170,171,172,173,174,175,176,177,178,179,180,181,182,183,184,185,186,187,188,189,190,191,192,193,194,195,196,197,198,199,200,201,202,203,204,205,206,207,208,209,210,211,212,213,214,215,216,217,218,219,220,221,222,223,224,225,226,227,228,229,230,231,232,233,234,235,236,237,238,239,240,241,242,243,244,245,246,247,248,249,250,251,252,253,254,255,256,257,258,259,268,269,270,271,274,275,278,279,280,281,282,283,286,287,290,291,292,293,294,295,304,305,306,307,308,309,312,313,316,317,318,319,328,329,330,331,333,337,340,341,342,343,352,353,354,355,358,362,364,365,366,367,368,372,376,377,378,379,382,386,388,389,390,391,393,397,400,401,402,403,412,413,414,415,417,419,421,423,424,425,426,427,429,433,436,437,438,439,442,446,448,449,450,451,452,453,454,456,457,458,460,461,462,463,464,465,467,468,469,471,472,473,474,475,477,478,481,482,484,485,486,487,488,492,496,497,498,499,500,501,503,504,505,507,508,509,510,511,512,516,520,521,522,523,524,526,528,530,532,533,534,535,538,542,544,545,546,547,556,557,558,559,563,567,568,569,570,571,574,578,580,581,582,583,584,587,588,591,592,593,594,595,604,605,606,607,616,617,618,619,621,625,628,629,630,631,640,641,642,643,645,649,652,653,654,655,664,665,666,667,669,673,676,677,678,679,681,685,688,689,690,691,693,694,697,698,700,701,702,703,705,707,709,711,712,713,714,715,716,720,724,725,726,727,736,737,738,739,748,749,750,751,760,761,762,763,766,770,772,773,774,775,779,783,784,785,786,787,796,797,798,799,801,803,805,807,808,809,810,811,820,821,822,823,832,833,834,835,836,837,839,840,841,843,844,845,846,847,856,857,858,859,868,869,870,871,874,878,880,881,882,883,892,893,894,895,904,907,908,911,912,915,916,917,918,919,928,929,930,931,940,941,942,943,952,953,954,955,956,957,958,960,961,962,964,965,966,967,976,977,978,979,983,987,988,989,990,991,1000,1001,1002,1003,1012,1013,1014,1015,1016,1017,1020,1021
```

### v3 failed ordinals

Count: 397. Digest:
`1e82f6014fd9ae0a16decd5d717ba4b78c0e06ae566ec033f8637bf87d43d9e6`.

```
25,62,96,260,261,262,263,264,265,266,267,272,273,276,277,284,285,288,289,296,297,298,299,300,301,302,303,310,311,314,315,320,321,322,323,324,325,326,327,332,334,335,336,338,339,344,345,346,347,348,349,350,351,356,357,359,360,361,363,369,370,371,373,374,375,380,381,383,384,385,387,392,394,395,396,398,399,404,405,406,407,408,409,410,411,416,418,420,422,428,430,431,432,434,435,440,441,443,444,445,447,455,459,466,470,476,479,480,483,489,490,491,493,494,495,502,506,513,514,515,517,518,519,525,527,529,531,536,537,539,540,541,543,548,549,550,551,552,553,554,555,560,561,562,564,565,566,572,573,575,576,577,579,585,586,589,590,596,597,598,599,600,601,602,603,608,609,610,611,612,613,614,615,620,622,623,624,626,627,632,633,634,635,636,637,638,639,644,646,647,648,650,651,656,657,658,659,660,661,662,663,668,670,671,672,674,675,680,682,683,684,686,687,692,695,696,699,704,706,708,710,717,718,719,721,722,723,728,729,730,731,732,733,734,735,740,741,742,743,744,745,746,747,752,753,754,755,756,757,758,759,764,765,767,768,769,771,776,777,778,780,781,782,788,789,790,791,792,793,794,795,800,802,804,806,812,813,814,815,816,817,818,819,824,825,826,827,828,829,830,831,838,842,848,849,850,851,852,853,854,855,860,861,862,863,864,865,866,867,872,873,875,876,877,879,884,885,886,887,888,889,890,891,896,897,898,899,900,901,902,903,905,906,909,910,913,914,920,921,922,923,924,925,926,927,932,933,934,935,936,937,938,939,944,945,946,947,948,949,950,951,959,963,968,969,970,971,972,973,974,975,980,981,982,984,985,986,992,993,994,995,996,997,998,999,1004,1005,1006,1007,1008,1009,1010,1011,1018,1019,1022,1023
```

The set relationship is exact:

- `v1 ∩ v3 = ∅`
- `v1 \ v3 = v1` (627)
- `v3 \ v1 = v3` (397)
- `v1 ∪ v3 = U` (1,024)

The two evaluator versions partitioned the same frozen episode inputs by
termination outcome. v1 falsely rejected every `goal_reached` ordinal. The
v3 correction accepted those 627 but falsely rejected every
`step_budget_exhausted` ordinal.

## Representative reconstruction

Ordinal 25 is in the v3-only set. Its immutable authority shard reports:

- semantic trace: 24 executed steps;
- final executed step index: 23, non-terminal and unsuccessful;
- denied attempt index: 24, reason `step_budget_exhausted`;
- no step index 24 was sent to the environment.

Each of its five parent-owned sessions has the same legal tail:

```
row 72  step           step_index=23 terminal=false success=false
row 73  observe
row 74  valid_actions
row 75  stop           reason=step_budget_exhausted
```

The parent protocol independently rejects a `step` when
`session.step_count >= request.step_budget`; it accepted the above trace and
sealed a count of 24. The v3 gate nevertheless entered a `stop`-only state
immediately after row 72 because the count had become 24. It therefore
reported both rows 73 and 74 as
`terminal_or_budget_step_not_followed_by_stop`.

Ordinal 0 is a v1-only control. Its parent-owned primary tail is:

```
row 24  step           step_index=7 terminal=true success=true
row 25  stop           reason=goal_reached
```

That is the direct terminal path fixed before v3. The two examples and the
full census point to evaluator false negatives, not a candidate call-order or
budget defect.

## Normal termination-path census

The candidate and parent protocol jointly permit these stop locations:

| Candidate outcome | Parent-owned call suffix |
| --- | --- |
| `goal_reached`, `environment_terminal` | terminal/success `step -> stop` |
| `step_budget_exhausted` | nonterminal last `step -> observe -> valid_actions -> stop` |
| `operator_stop_requested`, `post_observation_mismatch` | `observe -> stop` |
| `no_valid_actions`, `policy_abstained`, `proposal_not_in_evaluator_valid_set` | `valid_actions -> stop` |
| RunLease witness/binding/denial | `valid_actions -> stop` |
| caught error/finally | `stop` from any live parent state after reset |

The parent state machine allows `stop` from `need_observe`,
`need_valid_actions`, or `after_valid_actions`; it forbids a step unless it is
in `after_valid_actions` and strictly below budget. A terminal/success result
adds the stricter candidate invariant that the next operation must be
`stop`.

## Minimal verifier correction and controls

The corrected audit mirrors those independently enforced parent states:

- an ordinary nonterminal step returns to `need_observe`, including step 24;
- an attempted step 25 is still rejected as `step_budget_exceeded`;
- terminal/success steps enter `must_stop`;
- normal and error termination may stop from any live parent state;
- post-stop activity, activity after a terminal step, missing stop, digest
  mismatch, step-index mismatch, and action binding checks remain fail-closed.

The final synthetic test set would fail under the superseded audit as
expected: 8 failed and 13 passed. The failures are the exact-budget denial
path, both observe-stage stop paths, the reset/observe/nonterminal-step
error/finally positions, and the over-budget counter's previously masked
step. After the correction, all 21 call-order tests pass.

As an evidence-only cross-check, the corrected auditor was streamed over all
5,120 parent sessions in each sealed raw file:

| Evidence | Sessions | `goal_reached` | `step_budget_exhausted` | Audit failures |
| --- | ---: | ---: | ---: | ---: |
| v1 | 5,120 | 3,135 | 1,985 | 0 |
| v3 | 5,120 | 3,135 | 1,985 | 0 |

This cross-check is not a new capability execution or verdict. A new
write-once attempt requires a separately committed and approved v4
preregistration.
