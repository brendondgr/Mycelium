# Mycelium Project Brief

## Executive Summary

Mycelium is a lab intelligence platform designed to help research teams discover, organize, and act on information more effectively. The system is centered around the idea of a living research network: papers, grants, fellowships, lab goals, student interests, project needs, and team knowledge are continuously gathered, connected, and transformed into useful guidance.

The product is intended for academic labs, graduate students, principal investigators, and research teams that need help keeping up with literature, funding opportunities, fellowships, project direction, and team-wide knowledge. Rather than acting as a generic chatbot or simple paper summarizer, Mycelium aims to become a personalized research scout for the lab.

The mascot and agent identity for the system is Mylo, the Mushroom Scout. Mylo represents the system's role: searching through large research ecosystems, finding useful information, connecting hidden ideas, and guiding teams toward relevant opportunities.

## Project Vision

The long-term vision for Mycelium is to create a personalized research operations platform for labs.

The platform should help answer questions such as:

- What new papers matter to this lab?
- Which grants fit the lab's current goals?
- Which fellowships are relevant to specific students?
- What projects, people, and research directions are connected?
- What knowledge has the team already accumulated?
- What should the lab pay attention to next?
- What opportunities are time-sensitive?
- What areas of research are emerging or underexplored?

Mycelium is meant to function as a living research companion that continuously builds context around the lab and uses that context to provide better recommendations, alerts, summaries, and strategic guidance.

## Core Problem

Research labs often struggle with fragmented information.

Important knowledge is spread across:

- publications
- PDFs
- grant pages
- fellowship databases
- lab websites
- student notes
- meeting discussions
- project documents
- Slack or Discord messages
- individual researcher interests
- advisor and student goals

As a result, labs can miss relevant papers, overlook funding opportunities, duplicate effort, lose track of prior discussions, or fail to connect students with opportunities that fit their goals.

Mycelium addresses this by creating a system that understands both the external research landscape and the internal structure of a lab.

## Product Concept

Mycelium is built around four major ideas:

### 1. Research Discovery

The system monitors research areas relevant to the lab and identifies papers, methods, datasets, claims, and emerging directions that may matter to current projects.

This includes literature search, paper ranking, research digests, and summaries tailored to the lab's profile.

### 2. Lab Profile Intelligence

Mycelium builds an evolving profile of the lab, including its research goals, active projects, major methods, funding needs, student interests, and strategic direction.

This allows the platform to make recommendations that are specific to the lab rather than generic across all researchers.

### 3. Opportunity Matching

The platform searches for and recommends grants, fellowships, calls for papers, workshops, and other research opportunities.

These recommendations are tailored to the lab and its members, including eligibility, research fit, deadline timing, and relevance to current goals.

### 4. Team-Based Knowledge Integration

Mycelium is designed to eventually integrate with communication platforms such as Discord and Slack so that team-based knowledge can be captured in real time.

The goal is for important discussions, decisions, updates, and research insights to become part of the lab's living knowledge environment instead of being lost in chat history.

## Current Development Focus

The current focus is on building the infrastructure and backend systems for scraping, collecting, filtering, and processing information.

This includes the foundational systems needed to gather information from research sources, funding pages, fellowship listings, lab-related documents, and other external resources.

At this stage, the priority is not to build the final polished user interface. The immediate goal is to create the reliable backend foundation that can support:

- research information scraping
- source collection
- grant and fellowship discovery
- document ingestion
- information filtering
- relevance scoring
- profile-aware recommendations
- structured report generation
- future integration with team communication platforms

Once this infrastructure is stable, the platform can expand into richer front-end experiences, dashboards, and real-time collaboration features.

## Role of the Knowledge Graph

The knowledge graph is a core part of the Mycelium concept, but it is not meant to be exposed as a technical feature first.

Instead, the knowledge graph functions as the platform's internal memory and relationship layer.

It helps connect:

- lab goals
- research projects
- papers
- claims
- people
- skills
- grants
- fellowships
- deadlines
- research topics
- prior discussions
- team decisions

The knowledge graph allows Mycelium to reason across relationships rather than treating every paper, opportunity, or message as an isolated item.

For example, instead of simply saying, "Here is a grant," Mycelium should eventually be able to say:

> This grant fits the lab because it aligns with a current project, supports a student's research direction, matches the lab's prior work, and has a deadline that is still actionable.

The exact structure of the knowledge graph can evolve over time. The important point is that Mycelium uses the graph as a living integration layer for lab memory, research context, and opportunity matching.

## Target Users

### Principal Investigators

PIs need to track research direction, funding opportunities, student progress, collaborations, and publication strategy. Mycelium can help by providing lab-level intelligence, funding alerts, research summaries, and strategic recommendations.

### Graduate Students

Graduate students need help finding papers, fellowships, conferences, research gaps, and project direction. Mycelium can provide personalized research monitoring and opportunity matching based on individual goals and academic stage.

### Research Teams

Teams need shared memory. Mycelium can help preserve important knowledge from meetings, chats, papers, reports, and project updates so the group can stay aligned.

### Grant and Proposal Teams

Proposal writing requires literature support, funding alignment, deadlines, and evidence. Mycelium can support grant discovery, proposal readiness, and research background generation.

## Core Features

### Personalized Research Goals

Each lab and lab member can have research goals that guide the system's recommendations.

These goals help determine which papers, grants, fellowships, collaborators, and project ideas are relevant.

### Literature Discovery

Mycelium monitors the research landscape and identifies papers that match the lab's interests.

The goal is not simply to retrieve papers, but to explain why they matter.

### Research Digests

The system can generate recurring research briefs summarizing important papers, trends, and opportunities.

These digests should be tailored to the lab's current projects and goals.

### Grant Alerts

Mycelium identifies grant opportunities that fit the lab's research areas, funding needs, and strategic direction.

Grant alerts should include explanations of fit, deadlines, potential relevance, and missing materials when possible.

### Fellowship Matching

The platform recommends fellowships and student opportunities based on individual researcher profiles.

This can include academic stage, research area, skills, career goals, and eligibility constraints.

### Lab Strategy Support

Mycelium should help labs think about what to pursue next by connecting literature trends, funding opportunities, team capabilities, and research gaps.

### Team Knowledge Capture

Future integrations with Discord and Slack will allow Mycelium to capture useful team discussions, project updates, and decisions in real time.

This makes the system more than a static research database. It becomes a living team memory.

### Project and Opportunity Awareness

The platform should help labs see which projects are active, which opportunities are upcoming, and which research directions are gaining momentum.

## Mylo: The Mascot and Agent Identity

Mylo is the mascot and agent identity for Mycelium.

He is a Mushroom Scout who represents the platform's role as a guide through the research ecosystem.

Mylo's symbolic purpose:

- searches for literature
- finds funding opportunities
- connects ideas
- guides research planning
- helps teams stay aligned
- brings important discoveries back to the lab

Mylo gives the product a friendly and memorable identity while reinforcing the central metaphor of Mycelium: a living network of knowledge growing beneath the surface.

## Design Identity

The visual style of Mycelium should feel warm, organic, intelligent, and research-oriented.

The design direction combines:

- soft botanical visuals
- warm cream backgrounds
- forest and moss greens
- sage accents
- subtle gold highlights
- rounded cards
- clean dashboard elements
- mycelium-inspired connection lines
- flat vector mascot illustrations

The product should feel imaginative without becoming childish. It should remain professional enough for academic labs while still feeling distinct from generic AI tools.

## Near-Term Goals

The near-term goal is to create a working backend foundation for information collection and research intelligence.

Primary near-term priorities include:

- collecting research and opportunity data
- scraping relevant public sources
- filtering noisy information
- identifying useful papers, grants, and fellowships
- building lab and member profiles
- generating useful research and opportunity summaries
- preparing the system for knowledge graph integration
- designing early workflows for recurring digests and alerts

The first useful version should be able to produce personalized research and opportunity intelligence for a lab, even if the interface is still simple.

## Long-Term Goals

The long-term goal is to evolve Mycelium into a full lab intelligence platform.

Future capabilities may include:

- real-time Discord and Slack integration
- lab-wide shared research memory
- personalized student opportunity tracking
- grant readiness dashboards
- research strategy planning
- project progress awareness
- team collaboration insights
- automated research digests
- living literature reviews
- knowledge graph-powered recommendations
- publication and proposal support

Ultimately, Mycelium should help a lab understand what it knows, what it needs, what it should pursue, and what opportunities it should not miss.

## Product Positioning

Mycelium should not be positioned as a generic AI chatbot.

It should be positioned as:

> A living research intelligence system for labs.

A concise positioning statement:

> Mycelium helps research labs discover literature, connect knowledge, find grants and fellowships, and guide team strategy through personalized lab intelligence.

An alternative positioning statement:

> Mycelium is an AI research scout that builds a living profile of a lab and uses it to surface the papers, opportunities, and insights that matter most.

## Success Criteria

The project is successful if it can help a lab:

- find relevant papers faster
- identify grants and fellowships earlier
- connect opportunities to specific lab goals
- support students with personalized recommendations
- preserve useful team knowledge
- reduce duplicated research effort
- improve research planning and proposal preparation
- maintain a living memory of the lab's evolving work

The strongest version of Mycelium is not just a search tool. It is a system that helps research teams grow more strategically over time.

## Summary

Mycelium is a research intelligence platform for labs, built around the metaphor of a living knowledge network.

Its current focus is on backend infrastructure for scraping, collecting, filtering, and processing research and opportunity information. Over time, the system will grow into a team-aware platform with Discord and Slack integration, allowing lab knowledge to be captured and integrated in real time.

The platform combines personalized lab profiles, research discovery, grant and fellowship alerts, knowledge graph integration, and team-based memory into a unified research assistant.

Mylo, the Mushroom Scout, represents the product's purpose: to search, connect, find, and guide.

Mycelium's long-term aim is to become a living intelligence layer for research labs.
