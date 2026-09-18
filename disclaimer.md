# Disclaimer

## Independent Research

All architectural patterns, specifications, methodologies, and documentation in this repository were developed independently in a personal research and development environment. They represent the author's independent research and professional perspective, informed by two decades of experience in security architecture, governance, and risk management across multiple organisations.

## No Employer Affiliation

This work does not represent the systems, products, roadmap, intellectual property, or official stance of any current or former employer. No proprietary frameworks, internal tooling, confidential methodologies, or employer-specific implementations are described or referenced in this repository.

## Educational Purpose

The reference architecture, codified rules, invariant catalogues, and deployment patterns are published for educational and professional development purposes. They are designed to illustrate architectural principles for governance tooling and specification-driven agentic development, not to provide a production-ready system.

## Reference Implementation

This repository includes a working software implementation in `platform/`,
licensed separately under Apache 2.0.

It is a **reference implementation**: it exists to demonstrate that the rules in
this framework can be enforced by a system rather than described in a document.
It has not been through the operational hardening, penetration testing, or
sustained production use that a system holding real governance data requires.
The known limitations are stated plainly in
[platform/README.md](./platform/README.md) rather than left to be discovered.

Anyone deploying it takes on the full operational responsibility described in the
[AI tool lifecycle model](./architecture/ai-tool-lifecycle.md) and the
[shared responsibility model](./architecture/shared-responsibility.md): named
ownership, telemetry, versioning, incident response, and defined decommissioning
criteria. Speed of deployment does not reduce that obligation.

The software was developed independently, outside and unrelated to any
employment, using only public-domain frameworks and standards. It contains no
proprietary intellectual property, internal tooling, control libraries, or
operating-model detail belonging to any organisation.

## No Warranty

This material is provided as-is, without warranty of any kind, express or implied. The author assumes no liability for any use of the patterns, specifications, or methodologies described. Any implementation based on this work should be independently validated against the specific requirements, regulatory obligations, and risk appetite of the implementing organisation.

## Regulatory References

References to regulatory frameworks (DORA, NIST SP 800-207, OWASP, Central Bank of Ireland accountability framework) are the author's interpretation of publicly available standards and requirements. They do not constitute legal or compliance advice. Organisations should consult qualified legal and compliance professionals for authoritative guidance on regulatory obligations.

## Contact

For questions about this work, reach out via LinkedIn (link to follow).
