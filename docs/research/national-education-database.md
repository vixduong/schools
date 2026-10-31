# National education database (csdl.moet.gov.vn): must the platform report or sync?

Ticket: `.scratch/school-platform/issues/11-national-education-database.md`
Research date: 2026-10-31.
Context: multi-tenant SaaS for Vietnamese private and multi-level Schools (preschool to upper secondary), Django + Postgres.

This is research, not legal advice. "Not verified" marks anything I could not read at a primary source. Where only a provincial copy or a legal-portal summary was readable, I say so.

## 1. Bottom line

1. **Reporting is a duty of the school, and the rules do not carve out private schools.** Circular 42/2021/TT-BGDĐT applies to "cơ sở giáo dục mầm non, phổ thông, thường xuyên" with no public/private split (the only qualifier is the level). I read that as covering private schools; no text I found says so in words (inference, see 2.1).
2. **The default route is manual entry or Excel import on csdl.moet.gov.vn, by a school login issued by the Sở GDĐT** (provincial education department). The circular also names a second route, a data integration channel ("trục tích hợp dữ liệu"), and tells the school to run school-management software that "connects, reports and shares data" with the database.
3. **A machine route exists.** Vendors such as VNPT (vnEdu) and MISA (EMIS) sync with the ministry database, and the ministry runs a published API for digital learning records. The connection specs and the approval procedure are not public in a form I could read (Decision 4998/QĐ-BGDĐT text not found; no vendor onboarding page found).
4. **Recommendation:** MVP ships an **Excel/CSV export** shaped like the ministry import templates, plus the data-model fields the national system keys on (identifiers, see 6). Defer API sync until a real customer asks and the ministry's technical spec is in hand. Details in section 7.

## 2. Is reporting mandatory, and for private schools?

### 2.1 Legal basis

Primary source: Circular 42/2021/TT-BGDĐT, signed 30/12/2021, Official Gazette no. 85+86 of 17/01/2022. I downloaded the gazette PDF and read the text myself.
- Gazette entry: <https://congbao.chinhphu.vn/noi-dung-van-ban-so-42-2021-tt-bgddt-36476>
- PDF: <https://congbaocdn.chinhphu.vn/CongBaoCP/VanBan/2021/12/36476/39273-1-202285-8642-2021-tt-bgddt.pdf>
- Listing on vanban.chinhphu.vn: <https://vanban.chinhphu.vn/?pageid=27160&docid=205058&classid=1&typegroupid=6>

What it says (Vietnamese from the PDF):

- Điều 1.2(b) scope: "Các cơ sở giáo dục bao gồm: Cơ sở giáo dục mầm non, cơ sở giáo dục phổ thông, cơ sở giáo dục thường xuyên, cơ sở giáo dục đại học, trường cao đẳng có đào tạo ngành Giáo dục Mầm non". No ownership type is named, so it neither lists nor excludes private schools.
- Điều 11.5: preschool, general and continuing-education institutions "có trách nhiệm quản lý và tổ chức cập nhật báo cáo dữ liệu lên cơ sở dữ liệu giáo dục và đào tạo; bảo đảm dữ liệu đầy đủ, chính xác và báo cáo đúng thời hạn".
- Điều 17: the same institutions must "triển khai phần mềm quản lý trường học ... và kết nối, báo cáo chia sẻ dữ liệu với cơ sở dữ liệu giáo dục và đào tạo" and collect, update and report on time.
- Điều 9.5: school administrator accounts are issued by the Sở GDĐT or Phòng GDĐT that directly manages the school. The school then issues sub-accounts to its own staff.

Status: effective 14/02/2022 (the gazette PDF prints "2021", an evident typo; legal portals give 2022), replaced Circular 26/2019/TT-BGDĐT. I found no later replacement. A MOET 2024 letter and provincial 2026 letters still cite it as current (sections 3, 4). I did not check vbpl.vn for amendments (not verified).

Inference, flagged: since the circular regulates by education level and not ownership, private schools are in scope. The legal-portal summaries (caselaw.vn, congbao page) confirm that the text does not mention "tư thục" or "ngoài công lập" at all. A Sở GDĐT or counsel should confirm for each province before we promise customers anything.

### 2.2 Statistical reporting regime (the content and deadlines)

Circular 42, Điều 11.1 does not set content or deadlines itself; it refers to "quy định về chế độ báo cáo thống kê ngành giáo dục" and to ad hoc requests from MOET.

- Current statistics regime: Circular 25/2024/TT-BGDĐT (issued 25/12/2024, effective 09/02/2025, replaces 24/2018). I could not open the full text (hoatieu.vn returned 403) and did not read its "đối tượng áp dụng" article, so whether it names private schools is **not verified**.
- Periods, from a legal-portal summary of Circular 25/2024 (secondary source, not verified at the circular): preschool, general, continuing and special education each report twice per school year. Start of year: reference date 30/9, due 30/10. End of year: reference date 31/5, due 30/6. Source: <https://luatvietnam.vn/tin-van-ban-moi/ky-bao-cao-va-thoi-han-bao-cao-thong-ke-nganh-giao-duc-tu-ngay-09-02-2025-186-100784-article.html>
- MOET Official Letter 4324/BGDĐT-CNTT (14/08/2024), which I read in full (PDF from a school host, text matches the MOET letterhead and number): tells the Sở GDĐT to "thực hiện nghiêm túc chế độ báo cáo thống kê giáo dục định kỳ đối với giáo dục mầm non, phổ thông và giáo dục thường xuyên cấp Trường/Trung tâm, Phòng, Sở GDĐT (kỳ đầu năm học và kỳ cuối năm học)". Copy: <https://cntt.pnt.edu.vn/api/upload/20250324ak44324_BGDDT-CNTT_trienkhai_kehoach.pdf>
- Same letter, section II.2: school-management software to be deployed in 100% of schools, with at minimum modules for learner records, staff, facilities, school health and finance, and to "đảm bảo kết nối thông suốt với cơ sở dữ liệu ngành giáo dục". It also asks for learner and teacher personal identification numbers (số định danh cá nhân) to be completely filled, and learning results updated "theo từng kỳ học" (each term).
- Flow: school reports to the Phòng GDĐT, which reports to the Sở GDĐT, which reports to the ministry. Source: MOET Official Letter 2201/BGDĐT-CNTT (27/05/2022), read through a legal-portal copy. It said data is entered on `csdl.moet.gov.vn` and the online system locks the prior year after a set date. <https://luatvietnam.vn/giao-duc/cong-van-2201-bgddt-cntt-2022-bao-cao-thong-ke-giao-duc-ky-cuoi-nam-hoc-2021-2022-315241-d6.html>

Data categories the database holds (Circular 42, Điều 2.1 and 5-7): school network and campuses, classes, staff (managers, teachers, staff, training, ratings), learners (profile, learning results, health), facilities and equipment, finance (income and spend).

Frequency in practice: two statistical reports per year, plus continuous upkeep of the roster, class and learner records, plus term learning results, plus a start-of-year "move data to the new school year" step done by the school inside the system (provincial letter relaying MOET letter 1362/KHCNTT-TT of 21/08/2026; I read the provincial letter, not the MOET original: <https://sonha.quangngai.gov.vn/upload/2006808/20260827/1.%20CV%20rà%20soát,%20cập%20nhật%20dữ%20liệu%20và%20thực%20hiện%20sáp%20nhập%20các%20cơ%20sở%20giáo%20dục%20trên%20Hệ%20thống%20cơ%20sở%20dữ%20liệu%20ngành%20giáo%20dục%20và%20đào%20tạo.pdf>).

Note the ministry unit names are shifting (Cục Công nghệ thông tin in 2021-2024 texts, Cục Khoa học, Công nghệ và Thông tin in 2026 texts). Treat contact points as moving.

## 3. Routes: manual, Excel, or API

| Route | Evidence | Status |
|---|---|---|
| Manual entry on csdl.moet.gov.vn | Circular 42 Điều 11.2 "qua tài khoản đã được cung cấp"; 2026 provincial letter walks through in-app steps (copy staff, classes, learners to the new year). | Confirmed |
| Excel import into csdl.moet.gov.vn | The ministry's own user manual for the primary-school edition (Hà Nội, 07/2019) has sections "Nhập danh sách học sinh từ excel", "Nhập lớp học từ excel", "Nhập danh sách nhân sự từ excel", "Nhập tổng kết kết quả học tập từ excel". Flow: download template, fill in, upload, download an error file. Copy: <https://thkhanhloi.ninhbinh.edu.vn/wp-content/uploads/2025/12/Tài-liệu-HDSD-Phần-mềm-CSDL-giáo-dục-mầm-non-và-giáo-dục-phổ-thông-phân-hệ-Tiểu-học.pdf> | Confirmed as of 2019 edition; current templates not verified |
| Data integration channel ("trục tích hợp dữ liệu") | Circular 42 Điều 11.2 and Điều 12.2 name it. Điều 14.1: MOET issues versioned technical data rules and connection rules and publishes them on its portal. | Legal basis confirmed; spec not read |
| Vendor software sync | Điều 14.2-14.3, see section 4. vnEdu and MISA say they sync. | Vendor claims only |
| Digital learning record (học bạ số) API | Decision 3016/QĐ-BGDĐT (31/10/2025): schools submit XML records through a ministry API; see 5. | Confirmed (secondary copy) |

Excel is therefore a real, ministry-supported ingest path for roster, class, staff and learning-result data. It is not a reporting-form template path: the two periodic statistical reports are filled in on the system, and the sources I read do not mention Excel for those forms (not verified).

## 4. Can vendors integrate, and how do they get approved?

What the circular provides (Điều 14, read in the gazette PDF):
1. MOET issues "quy định kỹ thuật về dữ liệu, quy định kỹ thuật về kết nối và hướng dẫn kết nối, trao đổi dữ liệu", in versions, published on its portal.
2. School-management software and local education databases "được hỗ trợ kết nối và trao đổi dữ liệu". The owning body of the software or local database contacts and works with MOET (via the IT department, Cục CNTT) to get guidance and support to connect.
3. A public list of school-management software that meets the data and connection rules is to be published on the ministry portal.
4. Contact in the circular: `csdl@moet.gov.vn` (Điều 13.1; some 2024-2026 provincial letters print `csdl@moet.edu.vn`, so confirm the live address).

So the procedure is: vendor (the software owner) contacts the ministry IT unit, receives the technical specs and support, and is then listed. I found no application form, fee, test environment, or credential process on a public page. **Not verified:** the actual onboarding steps, turnaround, and whether a vendor gets its own API credentials or only the school's account is used.

Technical data rules: Decision 4998/QĐ-BGDĐT (31/12/2021) "ban hành Quy định kỹ thuật về dữ liệu của cơ sở dữ liệu giáo dục và đào tạo". Its existence and title are confirmed by MOET Official Letter 4324 (reference no. 21 in its legal-basis list). Its contents (tables, fields, codes) I could not open. **Not verified.**

Vendors that claim integration (vendor material, not ministry-verified):
- vnEdu (VNPT): an article of 30/09/2022 says vnEdu IOC is synchronized with the ministry database and holds a "Giấy chứng nhận đáp ứng chuẩn kết nối và dữ liệu của Bộ Giáo dục và Đào tạo". That supports the idea that a conformance certificate exists. <https://giaoduc.net.vn/vnedu-ioc-buoc-tien-trong-quan-ly-nganh-giao-duc-bang-du-lieu-post230037.gd> A trade-press snippet also says schools "cập nhật đồng bộ dữ liệu giữa 2 hệ thống vnEdu và csdl.moet.gov.vn" (not opened; search snippet only).
- MISA EMIS: MISA publishes a Chrome extension "Kết nối MISA EMIS - CSDLQG" by which a school sets up sync once and pushes school, class, teacher, student, learning-result and health data to the national database. It is a store listing with 73 users, so weak evidence. <https://www.extscope.org/extension/iilkfgjgeabmafjfgcncbmipjinccmgc> It suggests the sync may drive the school's own session, not a vendor key (inference, unproven).
- Viettel SMAS: I found no source describing a SMAS sync with csdl.moet.gov.vn. Not verified.

## 5. Digital learning record (học bạ số) API: the one concrete integration spec I read

Decision 3016/QĐ-BGDĐT (31/10/2025) on the digital learning record format, read through a legal-portal copy (the portal says the text was cut after 100,000 characters; I did not read the tail): <https://luatvietnam.vn/giao-duc/quyet-dinh-3016-qd-bgddt-2025-chuan-hoa-dinh-dang-du-lieu-hoc-ba-so-440230-d1.html>

- Applies to general and continuing education institutions (primary to upper secondary) without singling out private schools. It does not name vendors as obligated parties, but the school software must meet ministry requirements (verify signatures, warn on expiring certificates).
- Format: XML (`<DANH_SACH_HOC_BA>`), UTF-8, XML Signature, dd/MM/yyyy dates, ISO 8601 signing times.
- Transport: the school submits through an API on the ministry digital-record database. Request carries a JSON auth block (token, username, SHA-256 password hash, unit code, school year, message ID, type, function code) and a content field that is the XML, gzip-compressed and Base64-encoded. Six transaction types: submit, check submit result, register signing certificate, check certificate registration, request recall, check recall.
- A school's signing certificate must be approved by its supervising authority before it can issue records.
- Validity: the page states it expires on 01/09/2026 unless replaced. It is now 31/10/2026, so a successor may exist. **Not verified.**
- Related: MOET Official Letter 2239/BGDĐT-KHCNTT (29/04/2026) told Sở GDĐT to sync digital learning records to the National Data Center (Ministry of Public Security) with extra fields (organisation identifier, commune/ward code, province code) and said schools use their existing csdl.moet.gov.vn accounts; schools without an account are listed by the Sở GDĐT and sent to the ministry for accounts. Vendors are not mentioned. Read via legal portal: <https://luatvietnam.vn/giao-duc/cong-van-2239-bgddt-khcntt-2026-huong-dan-ket-noi-dong-bo-du-lieu-hoc-ba-so-434141-d6.html>

This shows two things: (a) a school-side API exists for at least this data set, and (b) account issuance goes through the Sở GDĐT, which is an approval step the SaaS cannot skip.

## 6. NDXP / LGSP and data-sharing standards

- Circular 42 Điều 11.2 and 12.2 name a "trục tích hợp dữ liệu" / "trục kết nối trao đổi dữ liệu" without naming NDXP or LGSP. Điều 12.3 requires use to comply with data-ownership and personal-data law. Decree 13/2023/NĐ-CP on personal data protection is cited in MOET letter 4324.
- NDXP (Nền tảng tích hợp, chia sẻ dữ liệu quốc gia) links state agencies; LGSP is the ministry/province-level platform. Press and provincial sources I saw say every ministry and province had an LGSP by end of 2020. They are agency-to-agency platforms. I found **nothing** saying a private school, or a private vendor, connects to NDXP/LGSP directly, and nothing on MOET's own LGSP. **Not verified.** For our product, NDXP/LGSP is the ministry's concern, not ours.
- Identifiers (Circular 42 Điều 10): school, teacher/manager/staff, and learner each have a unique, immutable ID from first entry, never deleted (status changes only). The school ID is issued by the Sở or Phòng GDĐT. Letter 4324 and letter 2239 require the national personal identification number (số định danh cá nhân) for teachers and learners; foreign learners need an e-identity account under Decree 69/2024/NĐ-CP (per letter 2239).

## 7. Recommendation

**MVP: build an export, not a sync.** In order:

1. **Data model, now (cheap, hard to retrofit):** store on School, Staff and Student: the ministry school code (issued by the Sở/Phòng), the ministry learner/teacher IDs, the national personal ID number, ethnicity, birth place, class level and school-year membership, status history rather than deletes (mirrors Điều 10). Add a Class entity with the ministry level/age-group fields. These are the keys any later sync or import needs.
2. **Excel/CSV export in the MVP:** roster, class, staff and term results in the column layout of the csdl.moet.gov.vn import templates, so a school admin downloads from us and uploads to the ministry system. This matches a path the ministry itself documents (section 3), needs no ministry approval, and covers the actual obligation (keep the school's own login data current). Treat the template columns as something to fetch from a customer login and check, since I could only read the 2019 manual (not verified for 2026).
3. **No API sync in MVP.** Reasons: the specs (Decision 4998 and the connection guide) are not public in a form I could read; vendor onboarding runs through the ministry IT unit, with no published process or timeline; accounts come from each Sở GDĐT, so credentials are per school and per province; the spec is moving (Decision 3016 reaches its stated end on 01/09/2026, the ministry unit was renamed). Building against a spec we cannot test is likely rework.
4. **Phase 2 trigger:** begin the API path when (a) a paying customer asks, (b) we have contacted the ministry IT unit (`csdl@moet.gov.vn`), got Decision 4998 and the connection guide, and asked about conformance listing, and (c) we have one pilot school whose Sở GDĐT issued an account. The học bạ số API (section 5) is the first target because its transport is the best documented.
5. **Do not promise "mandatory compliance" to customers** until a Sở GDĐT or counsel confirms private-school coverage in a given province and the Circular 25/2024 scope.

## 8. Open items (not verified)

- Full text of Decision 4998/QĐ-BGDĐT and the current connection guide.
- Vendor onboarding procedure, credentials model, test environment, and the published list under Điều 14.3.
- Circular 25/2024/TT-BGDĐT scope article (private schools named or not) and the exact form list for preschool and general levels.
- Whether Decision 3016/QĐ-BGDĐT was replaced after 01/09/2026.
- Whether Circular 42/2021 has since been amended or replaced (no hit found; vbpl.vn not checked).
- Current Excel template layouts (only the 2019 manual was read).
- Any SMAS or generic vendor sync documentation.
- Provincial variations (extra provincial systems, e.g., Phòng/Sở local databases that Điều 15.5 allows).
