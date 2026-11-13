# RC8C3FB3D

## Question

What is the main idea of this paper, and who are its authors?

## Answer

**Main idea (#1):** Rescene-ESM is an Earth system model that puts a *frozen* (fixed, not retrained) 20.8-million-parameter AI weather model at its core, linked through a new coupler called YAHO to physically formulated ocean, sea-ice, land, river, carbon, and energy components. The point is to get the speed of ML weather models (it simulates ~1,000 years per day on a single GPU) while keeping the climate physically grounded — the couplings are added one at a time to show each contributes to realistic El Niño variability and teleconnections, and the full model reproduces observed 1979–2022 warming, routes runoff to 212 river gauges, and separates heatwave exposure between SSP1 and SSP3 futures by a factor of 4.7.

**Authors:** Minjong Cheon and Kaoru Kakinuma (2026).

## Evidence

### Reference numbers in this conversation

- #1: [paper] Rescene-ESM: an Earth system model built around a frozen AI weather model

### Function result: corpus_item

#1 [paper] Rescene-ESM: an Earth system model built around a frozen AI weather model
Authors: Minjong Cheon, Kaoru Kakinuma
Year: 2026
Link: https://www.semanticscholar.org/paper/e1c22d8441861158dd7f9e6021cb718096d3f29f
Still open/current: yes
Problem (Mycelium's reading): The high computational cost of Earth system models limits the exploration of scenarios and ensemble members, while existing machine-learning weather models coupled to oceans have produced weak El Niño variability or relied on climate-model output, and none effectively routes climate impacts through…
Method (Mycelium's reading): Rescene-ESM, an Earth system model using a coupler named YAHO that links a frozen 20.8-million-parameter AI weather model to physically formulated ocean, sea-ice, land, river, carbon, and energy components constrained by observations; the model uses an interactive mixed layer, an equatorial wave oc…
Setting (Mycelium's reading): Simulations of approximately 1,000 years on one graphics processing unit; evaluation against observed climate data from 1979-2022; routing of runoff to 212 river gauges; and future projections for SSP1 and SSP3 scenarios for the period 2081-2100.
Abstract:
Earth system models underpin climate projections, but their cost limits how many scenarios, ensemble members and impact pathways can be explored. Machine-learning weather models forecast as skillfully as physics-based models at a fraction of the cost, yet coupled to an ocean they have produced weak El Nino variability or have learned it from climate-model output, and none carries the climate through rivers to the people exposed to it. Here we present Rescene-ESM, an Earth system model whose coupler, YAHO, yokes a frozen 20.8-million-parameter AI weather model to physically formulated ocean, sea-ice, land, river, carbon and energy components constrained by observations. Adding the couplings one at a time shows what each contributes: over a climatological ocean the AI atmosphere varies from year to year by a third of the observed amount over the oceans, and an interactive mixed layer, an equatorial wave ocean, the residual of the observed sea surface temperature (SST) equation as stochastic forcing and the land's moisture flux raise this step by step and bring El Nino and its teleconnections, leaving the mean climate almost unchanged. The full model simulates about 1,000 years per day on one graphics processing unit, holds the observed climate for a thousand years without drift, reproduces the observed 1979-2022 global warming, carries forced change with a physically based structure around the frozen network (transient climate response 1.60 K), routes runoff to 212 river gauges with a median seasonal-cycle correlation of 0.79 and, driven by emissions, separates the heatwave exposure of an SSP1 and an SSP3 world by a factor of 4.7 in 2081-2100, three-quarters of it through the warmer climate.

### Reference cards in view

#1 item: [paper] Rescene-ESM: an Earth system model built around a frozen AI weather model
   paper · 2026
   read more: corpus_item(item='#1')
