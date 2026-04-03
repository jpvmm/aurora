# Aurora
---

## The One Liner:
A privacy first Obsidian assistant that is capable of remember everything in your vault for long periods of time.

## The Problem:
Obsidian is a great tool to store human knowledge, but it is super hard to find information when need
ed and can be a organization nightmare. The common solution to it is to just connect tools like claude code to the vault, which is not very great for privacy preserving objectives.

## What it is:
A desktop app that is capable to ingest your vault as a knowledge base, construct memories from your interactions with the assistant and create new knowledge mixing every information available. In Autora everything runs locally, preserving user privacy in all the steps and storing knowledge for the future safely.

## Core Principles:
- Everything must run locally.
- The setup must be easy.
- Privacy is the most important thing.
- It must be as cheap as possible.
- The assistant must help the user organize his ideas and thoughts.
- Everything must be tuned to PT-BR language.
- The system must learn with user interaction.

## How the system should work:
### Knowledge Based Creation:
The knowledge base creation will be based on .md files from an Obsidian vault. The knowledge base is the base that the assistant must use in order to consume information from Obsidian.

The knowledge base only concern is to manage information from the user Obsidian vault and nothing else. It must be anble to ingest notes, generated embeddings, store embeddings and update every time it is needed to be updated. It must use everything that QMD already uses.

The KB must be created as a CLI tool so the user can control it via terminal

#### Technology to be used:
QMD is a great tool to transform .md files in vector storage, we must use it: https://github.com/tobi/qmd as a tool.

### Assistant long term interaction memory:
The assistant must store interactions with the user and learn about them every time. Another key point of the assistant memory is to find new connection between interactions and notes from the knowledgegraph, this way being able to create new information to the user.

The agent memory must be a tool to the agent to use .

#### Technology to be used:
Graphiti (open-source) is a great tool to create agent memories as graphs: https://github.com/getzep/graphiti. We must use it as agent memory.

### Assistant:
The assistant is the touching point between the user and the system. The system must be able to handle knowledge base and memories from the user at anytime with speed and accuracy. For the first versions of the project the assistant must run as a CLI tool from anywhere in the computer, like Claude Code.

#### Technology to be used:
The assistant must be created using Agno agent framework and all it's capabilities and for model serving it must use llama.cpp.

## Key Features:
   ### CLI based:
      -The ingestion of .md file in folder vault must be done via CLI.
      -The CLI must be as user friendly possible.
      -The CLI tool must support: ingestion, deletion, updating and reading of information in the knowledge base.
      -The agent must be invoked via CLI like claude code.

   ### Assistant:
      -The agent memory must be concise and fast.
      -The agent must know when to search things in knowledge base (qmd), when to use long term memory (graphiti) and when to use a hybrid approach.
      -The agent must always be able to be invoked from anywhere with access to its memory.
      -The assistant **must run solely with open-source models through llama.cpp**.
      -The assistant **must always communicate using pt-br and only change languages when the user ask for**.
   ### Models setup:
      -The user can have full control on models setup.
      -The model setup must be easy and fast.
      -It must be easy to the user change models whenever its needed.

## Development process
   -You must create branches for every new feature.
   -You must think long and hard when planning.
   -Always test newly created features from the user perspective.
   -For long running processes (like ingestion) you must create beautiful logs to the user follow.

## Project technologies
   -Python3.13
   -UV
   -Github
   -Agno
   -Graphiti
   -QMD
   -Docker
   -docker-compose
   -llama.cpp

