# Data model

Original job results and events remain immutable. The performance projection is
derived on read and carries a version, run, order, per-model metrics, attempt
references and sources. A timing sample must be finite, nonnegative and present.
Zero is a valid measurement; missing is not zero. Success timing requires the
stored pass verdict and normal termination. Each diagnostic states its coverage.

The browser groups events by task/model, projects stable node identities, and
patches only changed content. It keeps event sequence separate from dependency
information. Delta text belongs to its model node. A result node comes only from
a recorded attempt result. Historical events populate immediately without live
animation; fresh delivered events may animate when visible.
