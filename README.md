# CodeSage AI

**An LLM-powered engineering knowledge platform: ask questions about your codebase, get onboarding guides, and get warned when a pull request looks like a past incident.**

> This repository is a project write-up. CodeSage AI was built at an internal company AI hackathon, where it was a finalist, and the source code is not public.

## The problem

Answers about a large engineering organization are spread across hundreds of repositories, incident tickets, and post-incident reviews. New engineers ask the same questions again and again, and the lessons from past incidents rarely reach the next pull request that repeats them.

## What it does

- **Ask the codebase:** a chat that answers questions using retrieved code and documents, with source references.
- **Linked wiki pages:** an LLM pipeline that ingests repositories, incidents, and RCAs, links shared entities in a knowledge graph, and synthesizes wiki pages that span documents.
- **GuardRail:** for an open pull request, embeds the changed code, finds similar past incidents, applies rule-based checks (for example, dependency or config changes), and returns alerts ranked by severity, with recommendations.
- **Auto-Fix:**
  - given an incident description, ranks the most relevant files in the repository and fetches them concurrently within a token budget
  - adds similar past incidents as context and asks the LLM for a single-file fix
  - opens a pull request with the patch, or pushes it to an existing PR branch
- **Sprint helper:** pulls active sprint stories from the issue tracker and drafts PR templates for them.

## Architecture

```
React + Vite UI  ──HTTP──▶  FastAPI backend
                               ├── GitHub REST API   (repos, PRs, diffs, commits)
                               ├── Jira REST API     (sprint stories)
                               ├── LLM + embeddings  (answers, fixes)
                               ├── ChromaDB          (vector store: code, incidents)
                               └── NetworkX          (entity knowledge graph)
```

## Scale at the hackathon

- Indexed **53,000 documents**: 561 repositories, 1,386 incidents, and 43 RCAs
- Individual, team, and org knowledge bases modeled for **1,287 users**, to reduce LLM hallucinations on organization-specific questions

## Tech

Python · FastAPI · React 18 · Vite · ChromaDB · NetworkX · OpenAI-compatible LLM and embedding APIs · GitHub and Jira REST APIs · asyncio
