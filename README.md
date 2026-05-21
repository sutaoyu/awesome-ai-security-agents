# An Awesome List for AI Security Agents

We curate an Awesome List of **AI security agents** , specifically addressing:

- **Agents for Security**: Research and tools using AI agents to enhance cybersecurity defenses

- **Security of Agents**: Techniques to protect AI agents themselves from adversarial attacks


**Curated resources** including:  

🔬 *Research Papers* | 💻 *Open-Source Projects* | ✍️ *Technical Blogs* | 📂 *Benchmarks*

> Continuously updated with state-of-the-art developments in AI-powered security agents.


## 🔬 *Research Papers* 

> 📖 for papers accepted by reputed conferences/journals.

* 📖 [May 2025] **"Agent Security Bench (ASB): Formalizing and Benchmarking Attacks and Defenses in LLM-based Agents."** *Hanrong Zhang (Zhejiang University) et al.* ICLR 2025. [[paper](https://arxiv.org/abs/2410.02644)] [[code](https://github.com/agiresearch/ASB)] 

* [Apr 2025] **"WASP: Benchmarking Web Agent Security Against Prompt Injection Attacks."** *Ivan Evtimov (FAIR at Meta) et al.* arxiv. [[paper](https://arxiv.org/abs/2504.18575)] [[code](https://github.com/facebookresearch/wasp)] 

* 📖 [Feb 2025] **"Multi-Agent Security Tax: Trading Off Security and Collaboration Capabilities in Multi-Agent Systems."** *Pierre Peigne-Lefebvre (PRISM Eval) et al.* AAAI 2025. [[paper](https://arxiv.org/abs/2502.19145)] [[code](https://github.com/apartresearch/prompt-worms)] 

* 📖 [Feb 2025] **"AI Agents Under Threat: A Survey of Key Security Challenges and Future Pathways."** *Zehang Deng (Swinburne University of Technology) et al.* ACM Computing Surveys. [[paper](https://dl.acm.org/doi/full/10.1145/3716628)]

* 📖 [Feb 2024] **"Secret Collusion among AI Agents: Multi-Agent Deception via Steganography."** *Sumeet Ramesh Motwani (UC Berkeley) et al.* NeurIPS 2024. [[paper](https://arxiv.org/pdf/2402.07510)]



## 💻 *Open-Source Projects* 

* ![Agentic Security Stars](https://img.shields.io/github/stars/msoedov/agentic_security) [Agentic Security](https://github.com/msoedov/agentic_security) - An open-source vulnerability scanner for Agent Workflows and Large Language Models (LLMs) Protecting AI systems from jailbreaks, fuzzing, and multimodal attacks.

* ![agentic-radar Stars](https://img.shields.io/github/stars/splx-ai/agentic-radar) [agentic-radar](https://github.com/splx-ai/agentic-radar) - A security scanner for your LLM agentic workflows.

* ![promptfoo](https://img.shields.io/github/stars/promptfoo/promptfoo) [promptfoo](https://github.com/promptfoo/promptfoo) - Test your prompts, agents, and RAGs. AI Red teaming, pentesting, and vulnerability scanning for LLMs. Compare performance of GPT, Claude, Gemini, Llama, and more. Simple declarative configs with command line and CI/CD integration.

* ![fast-llm-security-guardrails](https://img.shields.io/github/stars/ZenGuard-AI/fast-llm-security-guardrails) [fast-llm-security-guardrails](https://github.com/ZenGuard-AI/fast-llm-security-guardrails) - The fastest Trust Layer for AI Agents.



## ✍️ *Technical Blogs*

* [How OpenAI’s red team made ChatGPT agent into an AI fortress](https://venturebeat.com/security/openais-red-team-plan-make-chatgpt-agent-an-ai-fortress/) - LouisColumbus, July 18, 2025. [[Chinese Blog](https://www.secrss.com/articles/81124)]

* [Google's Approach for Secure AI Agents](https://research.google/pubs/an-introduction-to-googles-approach-for-secure-ai-agents/) - Google Research, May, 2025. [[pdf](https://storage.googleapis.com/gweb-research2023-media/pubtools/1018686.pdf)]

* [Agentic AI – Threats and Mitigations](https://genai.owasp.org/resource/agentic-ai-threats-and-mitigations/) -  GEN AI, February 17, 2025.

* [Understanding AI Agent Security](https://www.promptfoo.dev/blog/agent-security/) - Vanessa Sauter, February 14, 2025.

* [Blueprint for AI Agents in Cybersecurity](https://www.cybersec-automation.com/p/blueprint-for-ai-agents-in-cybersecurity) - Filip Stojkovski
& Dylan Williams, Nov 25, 2024.

<!-- START_REPORT -->
## 📅 每日安全情报追踪 (2026-05-21)

> 💡 *提示：本板块由 Gemini API 每日上午 09:00 自动抓取过去 24 小时内 arXiv、Hugging Face 与 GitHub 的最新动态并自动更新。*

While I cannot access the live internet or run real-time queries to fetch papers and repositories published in the **exact last 24 hours** (as my knowledge cutoff is January 2025 and I lack a live web-browsing tool), I can provide some of the most significant and recent cutting-edge papers and open-source projects in these categories up to my latest training. 

If you are monitoring these fields daily, here are highly relevant, state-of-the-art papers and projects matching your criteria:

---

### Category 1: Agents for Security (AI-Driven Defense & Offense)

#### 1. PentestGPT
*   **Description**: A highly popular open-source project designed to act as an autonomous penetration testing assistant. Built on top of LLMs, it features a three-tier agent architecture (Task Handler, Task Parser, and Local Observer) to guide testers through complex exploit paths, maintain state, and suggest next steps in real time.
*   **Link**: [https://github.com/GreyDGL/PentestGPT](https://github.com/GreyDGL/PentestGPT)

#### 2. AutoAttacker: A Framework for Autonomous Penetration Testing
*   **Description**: This academic paper introduces an end-to-end framework where LLM-based agents autonomously conduct penetration testing against target environments. It utilizes a feedback loop of trial-and-error, parsing command outputs to adapt tactics and execute multi-stage exploits without human intervention.
*   **Link**: [https://arxiv.org/abs/2403.01038](https://arxiv.org/abs/2403.01038) *(Note: ArXiv identifier for reference)*

#### 3. SecGPT
*   **Description**: An open-source cybersecurity agent framework designed to automate SOC (Security Operations Center) tasks, network traffic analysis, and vulnerability assessment. It allows developers to deploy specialized security agents that cooperate to handle incident response and threat intelligence analysis.
*   **Link**: [https://github.com/feiskyer/secgpt](https://github.com/feiskyer/secgpt) (or official community mirrors)

---

### Category 2: Security for Agents (Protecting LLM Agents)

#### 1. InjecAgent: Benchmarking Indirect Prompt Injection in LLM Agents
*   **Description**: A key paper and benchmark designed to evaluate how susceptible LLM agents are to indirect prompt injection attacks (where malicious instructions are embedded in external data, like emails or web pages, which the agent reads). It establishes a standard for testing agent safety against data-poisoning exploits.
*   **Link**: [https://arxiv.org/abs/2403.02691](https://arxiv.org/abs/2403.02691)

#### 2. Meta Prompt Guard
*   **Description**: An open-source, highly efficient model released on Hugging Face designed specifically to defend LLM agents against prompt injection and jailbreak attacks. It acts as an input-filtering agent that scans incoming system prompts and user inputs before they reach the core LLM agent.
*   **Link**: [https://huggingface.co/meta-llama/Prompt-Guard-86M](https://huggingface.co/meta-llama/Prompt-Guard-86M)

#### 3. Agent-Safety Benchmark
*   **Description**: An open-source benchmark repository designed to evaluate the safety risks of LLM agents across diverse scenarios, such as tool abuse, unauthorized financial transactions, and illegal physical world interactions. It helps developers test if safety alignments hold true when LLMs act as autonomous agents.
*   **Link**: [https://github.com/THU-coai/Agent-Safety](https://github.com/THU-coai/Agent-Safety)
<!-- END_REPORT -->


## 📂 *Benchmarks*

* ![ASB](https://img.shields.io/github/stars/agiresearch/ASB) [ASB](https://github.com/agiresearch/ASB) - Agent Security Bench (ASB): Formalizing and Benchmarking Attacks and Defenses in LLM-based Agents.

* ![wasp](https://img.shields.io/github/stars/facebookresearch/wasp) [wasp](https://github.com/facebookresearch/wasp) - Benchmarking Web Agent Security Against Prompt Injection Attacks.



