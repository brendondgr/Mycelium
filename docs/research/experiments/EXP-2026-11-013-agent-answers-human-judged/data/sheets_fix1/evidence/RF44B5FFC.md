# RF44B5FFC

## Question

According to this paper, how many days ahead do machine-learning forecasts of marine heatwaves stay skilful?

## Answer

According to the provided evidence, the paper evaluates machine-learning forecasts of marine heatwaves in the Northern Bay of Bengal for a range of 1-14 days #1.

## Evidence

### Evidence #1 [paper] Evaluation of 1-14-Day Machine-Learning Forecasts of Marine Heatwaves in the Northern Bay of Bengal Against Persistence Benchmarks
Authors: Abu Baser Mojumder
Venue: Zenodo (CERN European Organization for Nuclear Research)
Year: 2026
Link: https://doi.org/10.5281/zenodo.24030524
Still open/current: yes
Problem (Mycelium's reading): Evaluation of 1-14-day machine-learning forecasts of marine heatwaves in the Northern Bay of Bengal against persistence benchmarks
Method (Mycelium's reading): Machine-learning forecasting evaluated against persistence benchmarks
Setting (Mycelium's reading): Northern Bay of Bengal
Abstract:
Code, processed data and results of the B.S. thesis "Evaluation of 1–14-Day Machine-Learning Forecasts of Marine Heatwaves in the Northern Bay of Bengal Against Persistence Benchmarks" (Department of Meteorology, University of Dhaka, 2026), as submitted.

### Evidence #2 [paper] Reply on RC2
Authors: Peihao Yang, Guodong Ye
Year: 2026
Link: https://doi.org/10.5194/egusphere-2026-262-cc1
Still open/current: yes
Abstract:
<strong class="journal-contentHeaderColor">Abstract.</strong> A primary challenge of machine learning to predict marine heatwave (MHW) for the south China sea (SCS) is the limited availability of observational data for model training. To address this issue, this study explores the viability of leveraging multi-member ensemble simulations from the Coupled Model Intercomparison Project Phase 6 (CMIP6), to construct an extensive, physically consistent training dataset for various machine learning models. After training on multiple CMIP6 ensemble members, the constructed models are evaluated for their predictive capacity regarding MHW in the SCS. The results also show that these machine learning-based methods can perform comparably to the existing dynamic models in terms of prediction performance, and in some cases even outperform the latter. Furthermore, by incorporating machine learning interpretability techniques, the key physical processes can also be elucidated from these predictions. That is to say, the new method is not a traditional "black box", but rather an effective tool that can possess certain physical transparency and scientific interpretability.

### Evidence #3 [paper] Application of Machine Learning Algorithms for Forecasting Sea Surface Temperature at Hon Dau Station
Authors: Do Thi Thu Ha, Nguyen Quoc Trinh, Nguyen The Duc, Nguyen Van Tung, Nguyen Thieu Hoa
Venue: VNU Journal of Science Earth and Environmental Sciences
Year: 2026
Link: https://doi.org/10.25073/2588-1094/vnuees.5463
Still open/current: yes
Problem (Mycelium's reading): Forecasting Sea Surface Temperature (SST) at Hon Dau station for climate studies, tropical cyclone prediction, and marine resource management.
Method (Mycelium's reading): Time series decomposition followed by the application of ARIMAX, SARIMAX, Prophet, and LSTM models for forecasting, and a linear regression model with Fourier harmonics for long-term projection.
Setting (Mycelium's reading): SST observations at Hon Dau station from 2000–2022.
Abstract:
Sea Surface Temperature (SST) plays a crucial role in climate studies, tropical cyclone prediction, and marine resource management. This study analyzes SST observations at Hon Dau station from 2000–2022 and applies ARIMAX, SARIMAX, Prophet, and LSTM models for SST forecasting. Time series decomposition was conducted to separate trend, seasonal, and residual components to guide model selection. Results indicate that ARIMAX, SARIMAX, and Prophet achieved high accuracy with mean absolute errors (MAE) of 0.82–0.92 °C, while LSTM performed less effectively due to data limitations. For long-term projection, a linear regression model with Fourier harmonics suggests an increase of approximately +1.7 °C in mean annual SST by 2100 relative to 2021, consistent with moderate climate scenarios. These findings highlight the potential of machine learning methods for short-term SST forecasting and emphasize the need for integrating multi-source data with physics-informed deep learning models to improve the reliability of climate and marine applications.

### Evidence #4 [paper] Machine learning weather prediction at the operational threshold: architectures, data, evaluation, and the observation-interface frontier
Authors: Qia Kang, Weiyu Ren, Boyu Gao
Venue: Zenodo (CERN European Organization for Nuclear Research)
Year: 2026
Link: https://doi.org/10.5281/zenodo.23788895
Still open/current: yes
Problem (Mycelium's reading): The transition of machine learning weather prediction (MLWP) from research to operational practice, specifically addressing bottlenecks in data provenance (ERA5 dependence) and evaluation metrics that mask critical failures like spectral deficit and over-smoothing.
Method (Mycelium's reading): A systematic review of six architectural families (spherical graph networks, 3D transformers, cascaded systems, diffusion/flow-based ensembles, geometric mesh-based ensembles, and hybrid models) and an analysis of data substrates and verification stacks. A four-tier experimental protocol is propose…
Setting (Mycelium's reading): Global weather forecasting models trained on reanalysis data (specifically ERA5), evaluated on 10-15 day forecasts at 0.25 degree resolution, including recent developments in end-to-end observation ingestion and multi-domain foundation models (2025-2026).
Abstract:
Machine learning weather prediction (MLWP) has moved from research demonstration into operational practice in roughly five years. Global models trained on reanalysis now produce ten- to fifteen-day forecasts at 0.25 degree resolution in seconds, and several match or exceed established numerical weather prediction (NWP) systems on standard verification metrics. This review examines what has been built, what it has been built on, and how it is being evaluated. Six architectural families are distinguished: spherical graph networks, three-dimensional transformers, cascaded multi-horizon systems, diffusion and flow-based generative ensembles, geometric mesh-based ensemble systems, and hybrid models that couple a differentiable dynamical core to learned physics. The data substrate receives detailed treatment, because ERA5 is a model-dependent product rather than a neutral training set, and every model trained on it inherits the analysis increments, parameterised tendencies, and changing observational coverage of that reanalysis. The verification stack is examined with equal care. Root-mean-square error and anomaly correlation are dominated by planetary-scale, slowly evolving flow, which makes them least sensitive to the failures that matter most: spectral deficit, over-smoothing of extremes, displacement error, and regime-dependent breakdown. A four-tier experimental protocol is proposed, combining reforecast benchmarking, out-of-distribution and regime-conditional testing, spectral and conservation diagnostics, and block bootstrap inference. The review then documents the frontier that emerged in 2025 and 2026, in which end-to-end systems ingest observations directly and bypass conventional data assimilation, and foundation models share one backbone across atmosphere, ocean, cryosphere, and atmospheric composition. The argument throughout is that the field's bottleneck has shifted from architecture to the observation interface and to evaluation practice, and that the credibility of MLWP over the next five years will rest on whether its claims survive out-of-distribution, conservation-aware, and statistically defensible scrutiny.

### Evidence #5 [paper] Multi-horizon forecasting of coastal high water temperature events for operational marine-heatwave early warning in South Korean aquaculture: a walk-forward benchmark of eleven statistical and deep-le
Authors: Young-Jin Kang, Ki-Hwan Kim, Seok Chan Jeong
Venue: Frontiers in Marine Science
Year: 2026
Link: https://doi.org/10.3389/fmars.2026.1887350
Still open/current: yes
Abstract:
Introduction High water temperature (HWT) marine-heatwave events along the southern coast of South Korea cause repeated mass mortalities in cage aquaculture of olive flounder (Paralichthys olivaceus), rock bream (Oplegnathus fasciatus), red sea bream (Pagrus major) and Korean rockfish (Sebastes schlegelii). Existing operational forecasts rely on coarse numerical ocean models that lack the temporal granularity and site specificity required by farm managers, while the recent wave of deep-learning sea surface temperature (SST) models has been tuned almost exclusively on smoother open-ocean grids. Methods We present the Hybrid GNN-BiLSTM, a 3.1 M-parameter graph–temporal architecture combining a weighted spatial GNN with a BiLSTM temporal core, reversible instance normalization (RevIN) and a persistence skip connection, and benchmark it against ten alternatives – three reference baselines (Persistence, Seasonal-naïve, Climatology), the ARIMAX statistical model, four lightweight or linear deep models (DLinear, PatchTST, N-HiTS, CNN-LSTM) and two attention-based models (Informer, Temporal Fusion Transformer) – on a five-year hourly insitu panel from 30 monitoring stations along the Tongyeong–Geoje–Yeosu coast (2020–2025) under a unified rolling-origin walk-forward protocol (720 h lookback, 168 h horizon, one forecast per station every 24 h across a 12-month validation window). Marine-heatwave detection is scored at tiered 26/28/30 °C operational thresholds. Results The Hybrid GNN-BiLSTM achieves the lowest 1 h RMSE (0.057 °C), 0.85 °C at h = 72 and 1.24 °C at h = 168, with the highest long-horizon residual skill of any deep model on this panel (SS_res = 0.71 at h = 72). CNNLSTM attains the lowest mean horizon root-mean-square error (RMSE = 0.636 °C) thanks to a nearly flat error curve, and PatchTST is competitive at short-to-medium horizons (0.694 °C mean). The Hybrid GNN-BiLSTM reaches F1 = 0.82 at 26 °C and F1 = 0.65 at 28 °C, and a probabilistic Gaussian negative-log-likelihood head supplies calibrated 90 % prediction intervals without post-hoc recalibration. Discussion A 38 h mean advisory lead time was demonstrated in the 2024 NIFS regional HWT alert period, indicating that a site-specific graph–temporal model can deliver operationally actionable early warning for coastal aquaculture.

### Evidence #6 [paper] Machine Learning Weather Prediction: Models, Verification and Limits
Authors: N Raji
Venue: International Journal of Information Technology Research Studies (IJITRS)
Year: 2026
Link: https://doi.org/10.63090/ijitrs/3139.3209.0040
Still open/current: yes
Problem (Mycelium's reading): Review of machine learning-based weather prediction models, their performance compared to physics-based models, and their limitations.
Method (Mycelium's reading): Literature review of neural networks trained on reanalysis data (2022-2025), covering deterministic, probabilistic, and hybrid models, as well as precipitation nowcasting.
Setting (Mycelium's reading): Global weather forecasting using models trained on four decades of ERA5 reanalysis data.
Abstract:
Between 2022 and 2025 a series of neural networks trained on four decades of reanalysis data began to match, and on many headline scores to beat, the best physics-based global weather forecasts, at a small fraction of the running cost. This review describes that change for an information technology readership and reports no new experiment. We begin with the numerical baseline and the ERA5 reanalysis on which nearly all of the models are trained. We then follow the deterministic models built on convolutions, neural operators, transformers and graph networks, the probabilistic and hybrid systems that came after them, and precipitation nowcasting from radar and satellite as a neighbouring problem. Benchmarks and published scores are then set beside the critical studies, which found forecasts that blur as lead time grows, weak physical balance at small scales, missing error growth from tiny perturbations, underestimated wind peaks in individual storms and poorer skill on record-breaking extremes. The same body of work also found realistic dynamical behaviour, and we report both sides. Compute cost, explainability and the dependence on numerical analyses for training and initial states close the review.

### Evidence #7 [paper] A Comparative Review of Machine Learning Algorithms for Weather Prediction: Performance, Challenges, and Future Perspectives
Authors: Harsh Bariya, Sheshang Degadwala
Venue: International Journal of Scientific Research in Artificial Intelligence and Machine Learning
Year: 2026
Link: https://doi.org/10.32628/ijsraiml2624111
Still open/current: yes
Problem (Mycelium's reading): Weather prediction is a complex forecasting problem due to interacting atmospheric variables across time and space, heterogeneous observations, and the need for reliability across different lead times and regimes.
Method (Mycelium's reading): Comparative review of traditional machine learning (Linear Regression, SVR, Decision Trees, Random Forest, XGBoost) and deep-learning algorithms (ANN, CNN, RNN, LSTM, GNN, Transformers, neural operators, probabilistic generative models), evaluating them based on data requirements, spatial/temporal …
Setting (Mycelium's reading): Literature review of representative systems including FourCastNet, Pangu-Weather, GraphCast, FuXi, GenCast, and the ECMWF Artificial Intelligence Forecasting System.
Abstract:
Weather prediction is a complex forecasting problem because atmospheric variables interact across time and space, observations are heterogeneous, and useful forecasts must remain reliable across different lead times and weather regimes. Numerical weather prediction (NWP) remains a major operational approach, while machine learning (ML) has rapidly developed as a complementary data-driven approach. This review examines traditional machine learning and modern deep-learning algorithms for weather prediction, with emphasis on Linear Regression, Support Vector Regression, Decision Trees, Random Forest, Gradient Boosting/XGBoost, Artificial Neural Networks, Convolutional Neural Networks, Recurrent Neural Networks, Long Short-Term Memory networks, Graph Neural Networks, Transformers, neural operators and probabilistic generative models. The literature is compared according to data requirements, spatial and temporal representation, computational cost, interpretability, uncertainty estimation and scalability. Representative systems such as FourCastNet, Pangu-Weather, GraphCast, FuXi, GenCast and the ECMWF Artificial Intelligence Forecasting System demonstrate the progression from feature-based prediction toward learned atmospheric-state evolution. Because published studies use different datasets, resolutions, variables, lead times and verification procedures, this review does not claim a universal best algorithm. Instead, it identifies a research opportunity for controlled comparisons using common data, chronological validation, multiple metrics, extreme-event testing and computational-cost reporting.

### Evidence #8 [paper] When the Stakes Are High: Trustworthy Machine Learning for Ocean and Coastal Hazard Forecasting
Authors: Ahmet Durap, Zekâi̇ Şen, Erdal Kesgin, Eyyup Ensar Başakın
Year: 2026
Link: https://doi.org/10.13140/rg.2.2.14518.25929
Still open/current: yes

### Evidence #9 [paper] Comparative evaluation of statistical and deep learning methods for high-frequency radar surface current forecasting in a narrow tropical strait
Authors: Dhava Gautama, Alifficionaldo Agpri Putra
Venue: Advances in statistical climatology, meteorology and oceanography
Year: 2026
Link: https://doi.org/10.5194/ascmo-12-221-2026
Still open/current: yes
Problem (Mycelium's reading): Accurate prediction of ocean surface currents in narrow waterways with strong tidal forcing.
Method (Mycelium's reading): Three-phase evaluation comparing persistence, tidal harmonics, classical time series, reduced-rank spatio-temporal statistical models, shallow machine learning, and deep learning (CNN, GRU, ConvLSTM-ED, BiEF) architectures for one-step-ahead and multi-step nowcasting.
Setting (Mycelium's reading): High-frequency (HF) radar surface current data in the Sunda Strait, Indonesia.
Abstract:
Accurate prediction of ocean surface currents is essential for maritime safety in narrow waterways with strong tidal forcing. This study presents a three-phase evaluation of forecasting methods for high-frequency (HF) radar surface currents in the Sunda Strait, Indonesia, where tidal currents regularly exceed 150 cm s −1 . Phase 1 compares twelve methods – persistence, tidal harmonics, classical time series, a reduced-rank spatio-temporal statistical model, shallow machine learning, and deep learning – for one-step-ahead prediction; evaluated consistently over all 291 grid cells and the full test period, the deep learning models achieve the lowest root-mean-square errors (RMSE) for both components, with the convolutional neural network (CNN) reaching 11.31 cm s −1 for the zonal component (skill score 0.50 relative to persistence) and the convolutional neural network–gated recurrent unit (CNN-GRU) reaching 15.44 cm s −1 for the meridional component (skill score 0.42); the pointwise classical statistical models (autoregressive integrated moving average, ARIMA; exponential smoothing) fall well below, while an empirical-orthogonal-function vector autoregression (EOF-VAR) that models spatial correlation closes most of the gap to deep learning, indicating that the neglect of spatial structure – not of nonlinearity – is the principal limitation of the classical baselines. Phase 2 examines lookback window length ( T = 3, 6, 12 h); CNN-gated recurrent unit (CNN-GRU) improves monotonically with longer lookback, reaching 11.21 and 15.41 cm s −1 at T = 12, while standalone CNN and GRU show no benefit. Phase 3 extends prediction to six-hour nowcasting using direct multi-step and autoregressive (ConvLSTM-ED, BiEF) architectures; under a controlled comparison (five seeds, identical training budget on one GPU), accuracy is governed by model capacity and plateaus near 1 M parameters (the 1.00 M CNN-GRU-MS-Small reaching 18.39 and 22.07 cm s −1 ; skill scores 0.77 and 0.72), and at matched capacity the direct and autoregressive architectures are statistically indistinguishable. The direct multi-step model is nonetheless preferred for operational nowcasting because it trains ∼2.5 times faster and runs ∼4.5 times faster at inference (a single forward pass versus sequential decoding). Diurnal error analysis, corroborated by concurrent wind observations from three coastal weather stations, reveals that zonal prediction errors correlate positively with afternoon sea-breeze wind enhancement (Spearman r s = 0.48 across the 24 diurnal-mean hours), while meridional errors follow a distinct diurnal pattern not explained by wind forcing. Relative errors of 3 %–7 % of the observed speed range are of the same order as those reported in calmer environments – though this normalisation partly reflects the strait's very large speed range – suggesting that deep learning does not break down in energetic strait settings.

### Evidence #10 [paper] Interpretable Machine Learning Surrogates for Short-Term Water-Level Forecasting at Ports: A Case Study of the Varna Hydromast Station
Authors: Antonios Parasyris, Vassiliki Metheniti, Georgios V. Kozyrakis, Milen Todorov, NIKOLAOS A. KAMPANIS, George Alexandrakis
Venue: Algorithms
Year: 2026
Link: https://doi.org/10.3390/a19110960
Still open/current: yes
Problem (Mycelium's reading): Short-term water-level forecasting at ports to support under-keel clearance, pilotage, and flood risk management, where regional ocean forecasting systems lack sufficient resolution for harbour basins.
Method (Mycelium's reading): Evaluation of machine learning surrogates (persistence, ridge regression, random forest, XGBoost, MLP, LSTM, PySR symbolic regression) using only the sensor's own recent history and deterministic harmonic cyclic features. The target is framed as a residual relative to the current observation.
Setting (Mycelium's reading): Varna Hydromast Station, port of Varna (Bulgarian Black Sea). Data split into training and a chronological hold-out period. Forecast horizons: 1, 3, 6, 12, and 24 hours.
Abstract:
The water level at ports governs under-keel clearance, pilotage windows, cargo operations and local flood risk, yet regional ocean forecasting systems resolve it at kilometre scales that may lie outside the harbour basin. This study evaluates a station-only machine learning surrogate that forecasts a single low-cost hydromast water-level sensor at the port of Varna (Bulgarian Black Sea) 1 to 24 h ahead, using only the sensor’s own recent history and deterministic harmonic (tidal and diurnal) cyclic features. The target is framed as a residual relative to the current observation, which keeps it bounded regardless of season or tidal phase. Persistence, ridge regression, random forest, XGBoost, a multilayer perceptron, a long short-term memory network and PySR symbolic regression are compared at horizons of 1, 3, 6, 12 and 24 h on a chronological hold-out period. Ridge regression is the most accurate model at 1–6 h, random forest is marginally best at 12 h, and PySR is best at 24 h, where all methods lie close to persistence. PySR reduces the residual problem to short closed-form expressions dominated by harmonic phase terms, at four of five horizons without any lagged water-level input. Grouping the methods into four interpretability tiers shows that, at this site, the intrinsically interpretable models are competitive with or better than the black-box alternatives at four of the five horizons.

### Evidence #11 [paper] Advancing subseasonal forecasting with machine learning.
Authors: Hannah Guan, Soukayna Mouatadid, Paulo Orenstein, Judah L. Cohen, Haiyu Dong, Zekun Ni, Jeremy D. Berman, Genevieve Flaspohler
Venue: Nature
Year: 2026
Link: https://doi.org/10.1038/s41586-026-11126-x
Still open/current: yes
Problem (Mycelium's reading): Forecast skill drops precipitously at subseasonal timescales (2–6 weeks ahead) due to compounding errors, systemic model biases, and the chaotic nature of the atmosphere.
Method (Mycelium's reading): Probabilistic bias correction, a machine learning framework that learns to correct historical probabilistic forecasts to reduce systematic error.
Setting (Mycelium's reading): Applied to leading dynamical and AI models from the European Centre for Medium-Range Weather Forecasts (ECMWF); evaluated in the 2025 real-time forecasting competition of ECMWF against models from six operational forecasting centres and 34 teams worldwide.
Abstract:
Decision-makers rely on weather forecasts to plant crops, manage wildfires, allocate water and energy and prepare for weather extremes1–3. Today, such forecasts enjoy unprecedented accuracy as far as 2 weeks thanks to steady advances in physics-based dynamical models and data-driven artificial intelligence models4–10. However, model skill drops precipitously at subseasonal timescales (2–6 weeks ahead) due to compounding errors, systemic model biases and the chaotic nature of the atmosphere11–15. To counter this degradation, we introduce probabilistic bias correction, a machine learning framework that substantially reduces systematic error by learning to correct historical probabilistic forecasts. When applied to the leading dynamical and artificial intelligence models from the European Centre for Medium-Range Weather Forecasts (ECMWF), probabilistic bias correction doubles the modest subseasonal skill of the AI Forecasting System16 and improves the skill of the operationally debiased dynamical model17 for 91% of pressure, 92% of temperature and 98% of precipitation targets. We designed probabilistic bias correction for operational deployment, and, in the 2025 real-time forecasting competition of ECMWF18, its global forecasts were the best for all weather variables and lead times, outperforming the dynamical models from six operational forecasting centres, an international dynamical multimodel ensemble, the AI Forecasting System of ECMWF and the forecasting systems of 34 teams worldwide. These probabilistic skill gains translate into more accurate prediction of extreme events and have the potential to improve agricultural planning, energy management and disaster preparedness in vulnerable communities19. The AI framework probabilistic bias correction is shown to correct weather forecast errors 2 to 6 weeks ahead and boost forecast skill, making it promising for improved extreme-weather prediction.

### Evidence #12 [paper] Short-Term Weather Prediction via Machine Learning Algorithms
Authors: Mateus M. B. Ribeiro, Felipe F. de Moura, Thiago Oliveira da Motta, Luis F. de Almeida, Mácio A. E. de Moraes
Venue: Zenodo (CERN European Organization for Nuclear Research)
Year: 2026
Link: https://doi.org/10.5281/zenodo.22984772
Still open/current: yes

### Evidence #13 [paper] Achieve Medium‐Range SST Forecast by Rolling 1‐Day Deep Learning
Authors: Nanxiang Huang, Jiangnan He, Wenfang Lu, Young‐Heon Jo
Venue: Geophysical Research Letters
Year: 2026
Link: https://doi.org/10.1029/2026gl123584
Still open/current: yes
Problem (Mycelium's reading): Cumulative error propagation and operational complexity in medium-range Sea Surface Temperature (SST) predictions using traditional Sequence-to-Sequence (Seq2Seq) models.
Method (Mycelium's reading): A framework named Multi-Earthformer utilizing two novel training strategies, Rolling Training and Multistep Training, to optimize autoregressive forecasting through a consistent 1-day rolling inference process.
Setting (Mycelium's reading): OISST data and independent in situ Argo observations.
Abstract:
Abstract Deep learning has revolutionized short‐term Sea Surface Temperature (SST) forecasting, but often struggles with cumulative error propagation and operational complexity in medium‐range predictions. To achieve lightweight and temporally continuous SST forecast, this study introduces two novel training strategies, Rolling Training and Multistep Training, to optimize autoregressive forecasting within an Earthformer neural network. By enforcing a consistent 1‐day rolling inference process, our framework eliminates temporal discontinuities and forecast ambiguity inherent in traditional Sequence‐to‐Sequence (Seq2Seq) models. We validate this optimized model, named Multi‐Earthformer, using OISST data and verify its robustness against independent in situ Argo observations. Results demonstrate that Multi‐Earthformer significantly enhances predictive skill beyond 15‐day lead times, suppressing seasonal systematic biases and maintaining stable, quasi‐linear error growth. Our approach offers a lightweight, physically intuitive paradigm that bridges the gap between daily synoptic variability and subseasonal‐to‐seasonal evolution, providing a scalable solution for reliable marine forecasting without the computational burden of traditional multi‐model ensembles.

### Evidence #14 [paper] Characterisation and forecasting of heatwaves using HWMId: Change-point based time series intervention modelling with machine learning for Western Maharashtra, India
Authors: N. Paul, B. Chanda, Navyasree Ponnaganti, S. Rathod, Dhananjay D. Nangare, K. S. Reddy
Venue: Theoretical and Applied Climatology
Year: 2026
Link: https://www.semanticscholar.org/paper/7f5d7bbb004b7358cc92a2b35f54b6babb9532c3
Still open/current: yes

### Evidence #15 [paper] Depth-Resolved Marine Heatwave Prediction in the Levantine Basin
Authors: D. N. H. Weerasinghe, S. Viswakula
Venue: Zenodo (CERN European Organization for Nuclear Research)
Year: 2026
Link: https://doi.org/10.5281/zenodo.24030956
Still open/current: yes
Problem (Mycelium's reading): Depth-resolved marine heatwave prediction in the Levantine Basin
Method (Mycelium's reading): Machine learning and explainable artificial intelligence
Setting (Mycelium's reading): Levantine Basin
Abstract:
Code and results for the IEEE ICAC 2026 paper "Depth-Resolved Marine Heatwave Prediction in the Levantine Basin Using Machine Learning and Explainable Artificial Intelligence".

### Evidence #16 [paper] Mathematical Modeling and Prediction of Heatwaves Using Time Series and Satellite Data
Authors: Joan P. Cobeña Cevallos, Vicente Marlón Villa Villa, Marco Vinicio Parra Chávez, Ana Carola Flores Mancheno
Venue: Athenea
Year: 2026
Link: https://doi.org/10.47460/athenea.v7i26.154
Still open/current: yes
Problem (Mycelium's reading): Modeling and predicting urban heatwaves in Guayaquil by capturing seasonality, persistence, and extreme temperature events using time series and satellite data.
Method (Mycelium's reading): Developed a retrospective modeling framework using dynamic harmonic regression with autoregressive integrated moving average (ARIMA) errors, compared against a persistence baseline via independent chronological validation. Evaluated a probabilistic forecasting approach and an alternative heatwave d…
Setting (Mycelium's reading): Guayaquil, Ecuador; using reanalysis-based air temperature (ERA5-Land), oceanic anomalies, and satellite-derived land surface temperature (MODIS).
Abstract:
Urban heatwaves require methods capable of capturing seasonality, persistence, and extreme temperature events. A retrospective modeling framework was developed for Guayaquil using reanalysis-based air temperature, oceanic anomalies, and satellite-derived land surface temperature. Temporal dynamics were represented using dynamic harmonic regression with autoregressive integrated moving average (ARIMA) errors and compared against a persistence baseline through independent chronological validation. A probabilistic forecasting approach and an alternative heatwave definition were also evaluated. Temporal modeling reduced the forecasting error for ERA5-Land maximum temperature relative to the naive baseline, whereas oceanic anomalies provided only marginal improvements for maximum temperature and degraded minimum temperature predictions. Probabilistic forecasting improved heatwave event detection, although it also increased the frequency of false alarms. MODIS observations revealed greater nighttime land surface te

### Evidence #17 [paper] Storm surge prediction using a surrogate hydrodynamic model based on long short-term memory networks
Authors: Villy Mik‐Meyer, Francisco C. Pereira, Morten Andreas Dahl Larsen, Jian Su, Martin Drews
Venue: Applied Ocean Research
Year: 2026
Link: https://doi.org/10.1016/j.apor.2026.105197
Still open/current: yes
Abstract:
Accurate storm surge prediction is essential for supporting early warning and preventive measures which reduce the risks associated with extreme sea levels. Physically based numerical models continue to improve in skill and resolution, but their high computational cost limits their use in large ensembles and long-term scenario analyses. Recent advances in machine learning offer a complementary pathway for efficient storm surge forecasting. Here, a machine-learning framework is developed to predict extreme sea levels in the North Sea and Baltic Sea. The model is based on 58 years of spatially distributed wind data and uses a Long Short-Term Memory (LSTM) architecture to capture the temporal dynamics driving water level variability. Compared to traditional physically based hydrodynamic models, the machine-learning approach requires only a fraction of the computational resources, enabling rapid probabilistic and large-ensemble forecasts across extended time periods. This efficiency is valuable for climate change research, where large ensembles are generally needed to address the combined uncertainty of climate and impact models but remain computationally infeasible using conventional approaches. By providing a scalable and resource-efficient alternative, this framework enables probabilistic storm surge prediction across timescales ranging from short-term forecasting to long-term climate projections over decades.

### Evidence #18 [paper] Ocean-E2E: Hybrid Physics-Based and Data-Driven Global Forecasting of Marine Heatwaves with End-to-End Neural Assimilation
Authors: Ruiqi Shu, Ruijian Gou, Yanfei Xiang, Xiaomeng Huang
Year: 2026
Link: https://doi.org/10.1145/3770855.3818893
Still open/current: yes
Abstract:
This work focuses on the end-to-end forecast of global extreme marine heatwaves (MHWs), which are unusually warm sea surface temperature events with profound impacts on marine ecosystems. Accurate prediction of extreme MHWs has significant scientific and financial worth. However, existing methods still have certain limitations in forecasting general patterns and extreme events. In this study, to address these issues, based on the physical nature of MHWs, we created a novel hybrid data-driven and numerical MHWs forecast framework Ocean-E2E, which is capable of 40-day accurate MHW forecasting with end-to-end data assimilation. Our framework significantly improves the forecast ability of MHWs by explicitly modeling the effect of oceanic mesoscale advection and air-sea interaction based on a dynamic kernel. Furthermore, Ocean-E2E is capable of end-to-end MHWs forecast and regional high-resolution prediction, allowing our framework to operate completely independently of numerical models while outperforming the current state-of-the-art ocean numerical/AI forecasting-assimilation models. Experimental results show that the proposed framework performs excellently on global-to-regional scales and short-to-long-term forecasts, especially in those most extreme MHWs. Overall, our model provides a framework for forecasting and understanding MHWs and other climate extremes. The source code is available at https://github.com/ChiyodaMomo01/Ocean-E2E.

### Evidence #19 [paper] Evaluation of the subseasonal forecast skill of marine heatwaves in the tropical Indian ocean
Authors: Linxi Meng, Xiaojing Li, Yunwei Yan
Venue: Climate Dynamics
Year: 2026
Link: https://doi.org/10.1007/s00382-026-08374-y
Still open/current: yes

### Evidence #20 [paper] A review of AI models for time-series prediction in ocean engineering applications: From classical neural networks to modern transformer architectures
Authors: Nerea Portillo Juan, Jorge Bris Moreno, Vicente Negro Valdecantos
Venue: Applied Ocean Research
Year: 2026
Link: https://doi.org/10.1016/j.apor.2026.105273
Still open/current: yes
Problem (Mycelium's reading): The need for time-series forecasting in ocean engineering applications (wave/metocean prediction, ship motion, trajectory, load, and structural response) and the evolution of AI models to address complex nonlinear marine system relationships.
Method (Mycelium's reading): A review analyzing the evolution of AI-based time-series forecasting models from early neural networks and recurrent/convolutional architectures to Transformer-based models, next-generation architectures (N-HiTS, TSMixer), and foundation models, examined through chronological and engineering perspe…
Setting (Mycelium's reading): Ocean engineering applications and AI-based forecasting literature.
Abstract:
Time-series forecasting is a key task in ocean engineering, supporting a wide range of applications, from wave and metocean prediction to ship motion and trajectory forecasting, wave-induced load prediction, offshore structural response and digital twins. In recent years, Artificial Intelligence (AI) has emerged as a powerful alternative and complement to traditional models, enabling the representation of complex nonlinear, multivariate, and temporal relationships in marine systems. This work presents a review of the evolution of AI-based time-series forecasting models in ocean engineering, highlighting the transition from early neural network approaches to recurrent and convolutional architectures and, more recently, Transformer-based models, next-generation architectures such as N-HiTS and TSMixer, and foundation models. The review analyses this evolution from both chronological and engineering perspectives, examining how different AI architectures have been applied to different ocean engineering problems and discussing their suitability according to the characteristics of each application. Finally, the review identifies current limitations related to data availability, computational requirements and physical consistency and discusses future research directions for the development and practical deployment of AI-based forecasting models in ocean engineering. • Transformer-based architectures dominate recent ocean forecasting studies. • Adoption of N-HiTS and TSMixer in ocean engineering remains limited. • Most advances in AI forecasting models have occurred since 2024. • Chinese institutions lead research on AI-based ocean forecasting. • Long-term forecasting in ocean engineering requires domain-specific horizon definitions.
