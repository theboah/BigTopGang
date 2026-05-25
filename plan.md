# Plan

Implement a system that takes audio for DnD sessions and creates a wiki using obsidian that builds knowledge with each session.

## End process

### Phase 1: Transcription

Take in a audio file and transcribe it into text. Store the transcription in sqlite database

### Phase 2: Summary

Use Gemma4 Ollama to summarise the transcript and publish the summary in the obsidian vault.

### Phase 3: Searching

Use Gemma4 Ollama agents to list out the creatures, locations, items, events, characters, factions etc from the transcript. We will have one agent work on the problem then another agent will review and critique its list. If the reviewer passes the list then it will be used to create a list of jobs which will go in a queue. If the reviewer fails the list then it will be sent back to the first agent to try again. The agent will be able to use tools to find articles in the obsidian vault to find existing creatures,locations etc. The agent will create a list of jobs which will be either update jobs or write jobs. Update jobs will be for existing creatures, locations etc that are present in the transcript and the job will check if there is new information worth updating the article about by comparing the current article and the new information in the transcript. Write jobs will be for new creatures, locations etc that are present in the transcript and the job will create a new article about it in the obsidian vault.

### Phase 4: Update

Each job that is an update job will be taken from the queue and used to update the relevant markdown files in the obsidian vault. This will include updating the summary, character profiles, location profiles, item profiles etc. The same agent, critic process will be used but agents will have a RAG semantic search as well as be able to read the markdown files in the obsidian vault to help them update the relevant information. The agents will also be able to read the graph view in obsidian to see how the different markdown files are connected and use that information to help them update the relevant markdown files. Each job can only write to a single file.

### Phase 5: Write

Each job that is a write job will be taken from the queue and used to write new markdown files in the obsidian vault. This will include writing new character profiles, location profiles, item profiles etc. The same agent, critic process will be used but agents will have a RAG semantic search as well as be able to read the markdown files in the obsidian vault to help them write the relevant information. The agents will also be able to read the graph view in obsidian to see how the different markdown files are connected and use that information to help them write the relevant markdown files.

### Phase 6: Link, Tag and Graph

Each new markdown file that is created or updated will be linked to other relevant markdown files in the obsidian vault. This will include linking characters to locations, items to characters, events to characters etc. Each markdown file will also be tagged with relevant tags to make it easier to find and organize the information in the vault. The graph view in obsidian will be used to visualize the connections between the different markdown files and see how they relate to each other.

## Implementation

Establish the python environment with requirements management and specific python version.
Implement transcription locally
Create models for Jobs including update jobs and write jobs. Create templates for the different types of markdown files such as summaries or templates for items, characters, locations etc.
Create tools to embed, access, update and write markdown files in the obsidian vault. Create tools to access the graph view in obsidian. Create a tool to access the RAG semantic search.
Create the agents and the process of critique.
Identify how to link articles together in this setup and tag them and implement that.
Identify how to produce relevant graphs in obsidian and implement that.

## Questions

I am using [Obsidian Local REST API](https://community.obsidian.md/plugins/obsidian-local-rest-api) but dont know how to setup certificates etc
Tools to access the obsidian vault or use plugins?
Hook up RAG semantic search to also be a search bar in obsidian vault.
How do we generate timelines?
