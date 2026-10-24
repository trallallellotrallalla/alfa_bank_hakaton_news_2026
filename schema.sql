--
-- PostgreSQL database dump
--

\restrict Qn2V39lK2V9ceEP2ZvpDsFNV3oepGfmg3C4L3IKHhu4zddoFLDDsH3Mk3kFd78I

-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: companies; Type: TABLE; Schema: public; Owner: arch
--

CREATE TABLE public.companies (
    uid text NOT NULL,
    org_type text,
    okfs_name text,
    company_age_years_gradation text,
    eco_mark_label text,
    mainokved_code text,
    mainokved_name text,
    negativemark boolean DEFAULT false,
    workers_fns_gradation text,
    workers_spark_gradation text,
    cl_type text,
    has_rko boolean DEFAULT false,
    has_gar boolean DEFAULT false,
    has_loa boolean DEFAULT false,
    has_lea boolean DEFAULT false,
    has_dep boolean DEFAULT false,
    has_zpp boolean DEFAULT false,
    fts_flag boolean DEFAULT false,
    fts_country_name text,
    has_factoring boolean DEFAULT false,
    revenue_company numeric,
    group_id text,
    city text,
    region text
);


ALTER TABLE public.companies OWNER TO arch;

--
-- Name: payments; Type: TABLE; Schema: public; Owner: arch
--

CREATE TABLE public.payments (
    payer text NOT NULL,
    beneficiary text NOT NULL,
    pay_amt numeric,
    pay_cnt integer
);


ALTER TABLE public.payments OWNER TO arch;

--
-- Name: person_company; Type: TABLE; Schema: public; Owner: arch
--

CREATE TABLE public.person_company (
    fid text NOT NULL,
    uid text NOT NULL
);


ALTER TABLE public.person_company OWNER TO arch;

--
-- Name: persons; Type: TABLE; Schema: public; Owner: arch
--

CREATE TABLE public.persons (
    fid text NOT NULL,
    city_name text,
    rc_name text
);


ALTER TABLE public.persons OWNER TO arch;

--
-- Name: products; Type: TABLE; Schema: public; Owner: arch
--

CREATE TABLE public.products (
    name text,
    price integer
);


ALTER TABLE public.products OWNER TO arch;

--
-- Name: top_counterparties; Type: MATERIALIZED VIEW; Schema: public; Owner: arch
--

CREATE MATERIALIZED VIEW public.top_counterparties AS
 SELECT payer AS uid,
    beneficiary AS counterparty,
    sum(pay_amt) AS total_amt,
    sum(pay_cnt) AS total_cnt,
    rank() OVER (PARTITION BY payer ORDER BY (sum(pay_amt)) DESC) AS rnk
   FROM public.payments
  GROUP BY payer, beneficiary
  WITH NO DATA;


ALTER MATERIALIZED VIEW public.top_counterparties OWNER TO arch;

--
-- Name: companies companies_pkey; Type: CONSTRAINT; Schema: public; Owner: arch
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_pkey PRIMARY KEY (uid);


--
-- Name: payments payments_pkey; Type: CONSTRAINT; Schema: public; Owner: arch
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_pkey PRIMARY KEY (payer, beneficiary);


--
-- Name: person_company person_company_pkey; Type: CONSTRAINT; Schema: public; Owner: arch
--

ALTER TABLE ONLY public.person_company
    ADD CONSTRAINT person_company_pkey PRIMARY KEY (fid, uid);


--
-- Name: persons persons_pkey; Type: CONSTRAINT; Schema: public; Owner: arch
--

ALTER TABLE ONLY public.persons
    ADD CONSTRAINT persons_pkey PRIMARY KEY (fid);


--
-- Name: idx_top_counterparties_uid; Type: INDEX; Schema: public; Owner: arch
--

CREATE INDEX idx_top_counterparties_uid ON public.top_counterparties USING btree (uid, rnk);


--
-- Name: payments payments_beneficiary_fkey; Type: FK CONSTRAINT; Schema: public; Owner: arch
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_beneficiary_fkey FOREIGN KEY (beneficiary) REFERENCES public.companies(uid) ON DELETE CASCADE;


--
-- Name: payments payments_payer_fkey; Type: FK CONSTRAINT; Schema: public; Owner: arch
--

ALTER TABLE ONLY public.payments
    ADD CONSTRAINT payments_payer_fkey FOREIGN KEY (payer) REFERENCES public.companies(uid) ON DELETE CASCADE;


--
-- Name: person_company person_company_fid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: arch
--

ALTER TABLE ONLY public.person_company
    ADD CONSTRAINT person_company_fid_fkey FOREIGN KEY (fid) REFERENCES public.persons(fid) ON DELETE CASCADE;


--
-- Name: person_company person_company_uid_fkey; Type: FK CONSTRAINT; Schema: public; Owner: arch
--

ALTER TABLE ONLY public.person_company
    ADD CONSTRAINT person_company_uid_fkey FOREIGN KEY (uid) REFERENCES public.companies(uid) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict Qn2V39lK2V9ceEP2ZvpDsFNV3oepGfmg3C4L3IKHhu4zddoFLDDsH3Mk3kFd78I

