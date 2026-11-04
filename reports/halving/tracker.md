# Tracker

```
Tracker. Baseline: items released in months 1-3 (median lead time; throughput = mean items per squad per month). Current: items released in months 5-6.
Progress = (baseline - current) / (baseline x 0.5) for lead time; (current - baseline) / baseline for throughput (target +100%). Shown value is clamped to 0-100%; raw is unclamped.

group              lead time                         baseline d current d     raw  shown
overall            idea_to_production_behind_flag         135.8     133.9    2.8%     3%
overall            idea_to_customer                       154.2     150.7    4.5%     5%
handling_payments  idea_to_production_behind_flag         135.7     138.0   -3.4%     0%
handling_payments  idea_to_customer                       155.1     156.0   -1.2%     0%
insight_reporting  idea_to_production_behind_flag         134.0     135.9   -2.8%     0%
insight_reporting  idea_to_customer                       151.7     154.9   -4.2%     0%
intake_claims      idea_to_production_behind_flag         136.7     128.6   11.8%    12%
intake_claims      idea_to_customer                       153.8     145.6   10.7%    11%
platform_access    idea_to_production_behind_flag         136.5     133.8    3.9%     4%
platform_access    idea_to_customer                       155.6     150.5    6.6%     7%
suppliers_comms    idea_to_production_behind_flag         135.7     135.5    0.2%     0%
suppliers_comms    idea_to_customer                       152.3     153.9   -2.1%     0%

group              throughput (items/squad/month)      baseline   current     raw  shown
overall                                                    32.2      33.0    2.5%     2%
handling_payments                                          31.3      31.5    0.5%     1%
insight_reporting                                          30.7      38.5   25.5%    26%
intake_claims                                              32.0      38.5   20.3%    20%
platform_access                                            34.3      28.0  -18.4%     0%
suppliers_comms                                            32.7      28.5  -12.8%     0%

Items released per squad per month: m1 m2 m3 m4 m5 m6
handling_payments   38  29  27  34  28  35
insight_reporting   33  30  29  35  40  37
intake_claims       28  28  40  28  41  36
platform_access     40  35  28  40  28  28
suppliers_comms     25  39  34  40  30  27

Overall median idea_to_customer / baseline, by month: m1 101%, m2 99%, m3 100%, m4 101%, m5 97%, m6 99%
```
