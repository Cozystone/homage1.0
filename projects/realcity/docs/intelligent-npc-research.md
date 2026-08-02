# Intelligent NPC Research Notes

This note captures the research pass requested for RealCity's NPC layer and the
implementation choices now reflected in `src/engine/agentCognition.js`.

## Sources Reviewed

- User-provided overview: https://healthy119.tistory.com/entry/%EC%A7%80%EB%8A%A5%ED%98%95-NPCNon-Player-Characters
  - Useful baseline taxonomy: finite state machines, behavior trees,
    pathfinding, crowd behavior, NLP, rule-based systems, reinforcement
    learning, neural methods, and hybrid systems.
- Park et al., "Generative Agents: Interactive Simulacra of Human Behavior":
  https://arxiv.org/abs/2304.03442
  - Core pattern adopted: memory stream, memory retrieval, reflection, planning,
    and believable daily/social behavior in a town.
- Hu et al., "A Survey on Large Language Model-Based Game Agents":
  https://arxiv.org/abs/2404.02039
  - Core pattern adopted: separate memory, reasoning, perception-action
    interfaces, communication protocols, and role differentiation.
- Zeng et al., "Perceive, Reflect, and Plan":
  https://arxiv.org/abs/2408.04168
  - Core pattern adopted: navigation agents should not simply react every step;
    they need spatial context, memory, reflection, and longer plans to avoid
    repeated or short-sighted movement.
- Rao et al., "Collaborative Quest Completion with LLM-driven NPCs in
  Minecraft": https://arxiv.org/abs/2407.03460
  - Core pattern adopted: LLM NPCs need rich game-state context and executable
    affordances, not only language.
- Kim et al., "Leveraging Large Language Models for Active Merchant NPCs":
  https://arxiv.org/abs/2412.11189
  - Core pattern adopted: specialized modules can make NPCs active rather than
    scripted; smaller/local models need grounded task schemas.
- Ren et al., "Emergence of Social Norms in Generative Agent Societies":
  https://arxiv.org/abs/2403.08251
  - Core pattern adopted: social norms should be represented and incorporated
    into planning, not left as text flavor.
- Hong et al., "GOBT": https://www.jmis.org/archive/view_article_pubreader?pid=jmis-10-4-321
  - Core pattern adopted: combine behavior trees with goal-oriented and utility
    selection so NPCs can adapt without rewriting every tree branch.
- Reynolds, "Steering Behaviors for Autonomous Characters":
  https://www.red3d.com/cwr/papers/1999/gdc99steer.html
  - Core pattern adopted: keep locomotion, path following, and obstacle
    avoidance below higher-level goals.
- ORCA: https://gamma-web.iacs.umd.edu/ORCA/
  - Core pattern adopted as a design target for smoother crowd-scale avoidance,
    while the current implementation keeps a lighter steering/collision layer.
- AI Town: https://github.com/a16z-infra/ai-town
  - Core pattern adopted: shared simulation state, persistent agents, and local
    LLM compatibility are a practical deployment shape for town-like worlds.

## RealCity Application

- High-level cognition is explicit:
  - observation
  - memory stream
  - recency/importance/relevance retrieval
  - reflection
  - utility/goal selection
  - behavior-tree execution
  - pathfinding, steering, taxi, collision, and social-norm enforcement
- The LLM is used as a high-level planner/speaker, not a per-frame controller.
- Every language plan must ground into RealCity affordances: sidewalks,
  crosswalks, buildings, taxis, relationships, and known places.
- Need-driven detours now require cognition evidence: the selected policy must
  be `need-detour`, and the city event explains that memory/reflection utility
  scoring changed the agent's route.
- Runtime verification now checks that NPC samples expose cognition metadata,
  reflection text, retrieved memories, utility scores, and diverse selected
  policies.
