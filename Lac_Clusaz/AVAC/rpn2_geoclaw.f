c======================================================================
       subroutine rpn2(ixy,maxm,meqn,mwaves,maux,mbc,mx,
     &                 ql,qr,auxl,auxr,fwave,s,amdq,apdq)
c======================================================================
c
c Solves normal Riemann problems for the 2D SHALLOW WATER equations
c     with topography:
c     #        h_t + (hu)_x + (hv)_y = 0                           #
c     #        (hu)_t + (hu^2 + 0.5gh^2)_x + (huv)_y = -ghb_x      #
c     #        (hv)_t + (huv)_x + (hv^2 + 0.5gh^2)_y = -ghb_y      #
c
c Modified from the standard GeoClaw rpn2_geoclaw.f to add a D-Claw
c static Coulomb yield check (George & Iverson 2014, J. Geophys. Res.).
c When both cells sharing an interface are EXACTLY at rest (u=v=0, set
c precisely by the floor-at-zero in src2.f90), the normal free surface
c gradient is tested against the Coulomb yield threshold mu*cos(theta).
c If the gradient is insufficient to overcome static friction, the two
c heights are equalized, zeroing the pressure-driven flux and keeping
c the material permanently at rest.  This is the 2D generalisation of
c the D-Claw 1D static yield check implemented in rp1_geoclaw.f90.
c
c Requires:
c   rheology_module : dx_avac, dy_avac  (set by b4step2.f90)
c   common /rheology/: mu, C, rho, imodel  (set by setprob.f90)

      use geoclaw_module, only: g => grav, drytol => dry_tolerance, rho
      use geoclaw_module, only: earth_radius, deg2rad
      use amr_module, only: mcapa

      use storm_module, only: pressure_forcing, pressure_index

      use rheology_module, only: dx_avac, dy_avac

      implicit none

      !input
      integer maxm,meqn,maux,mwaves,mbc,mx,ixy

      double precision  fwave(meqn, mwaves, 1-mbc:maxm+mbc)
      double precision  s(mwaves, 1-mbc:maxm+mbc)
      double precision  ql(meqn, 1-mbc:maxm+mbc)
      double precision  qr(meqn, 1-mbc:maxm+mbc)
      double precision  apdq(meqn,1-mbc:maxm+mbc)
      double precision  amdq(meqn,1-mbc:maxm+mbc)
      double precision  auxl(maux,1-mbc:maxm+mbc)
      double precision  auxr(maux,1-mbc:maxm+mbc)

      !local only
      integer m,i,mw,maxiter,mu,nv
      double precision wall(3)
      double precision fw(meqn,3)
      double precision sw(3)

      double precision hR,hL,huR,huL,uR,uL,hvR,hvL,vR,vL,phiR,phiL,pL,pR
      double precision bR,bL,sL,sR,sRoe1,sRoe2,sE1,sE2,uhat,chat
      double precision s1m,s2m
      double precision hstar,hstartest,hstarHLL,sLtest,sRtest
      double precision tw,dxdc

      logical rare1,rare2

      ! Rheological parameters for D-Claw static yield check
      double precision rho_rp, mu_rp, xi_rp, C_rp, ucr_rp
      integer imodel_rp
      common /rheology/ rho_rp, mu_rp, xi_rp, C_rp, ucr_rp, imodel_rp

      ! Local variables for the static yield check
      double precision dh_n, db_n, dx_n, costh_n, thresh_n, h_avg_n
      double precision eta_avg_n, hL_new, hR_new, spd_L, spd_R

      ! In case there is no pressure forcing
      pL = 0.d0
      pR = 0.d0

      ! initialize all components to 0
      fw(:,:) = 0.d0
      fwave(:,:,:) = 0.d0
      s(:,:) = 0.d0
      amdq(:,:) = 0.d0
      apdq(:,:) = 0.d0

      !loop through Riemann problems at each grid cell
      do i=2-mbc,mx+mbc

!-----------------------Initializing-----------------------------------
         !inform of a bad riemann problem from the start
         if((qr(1,i-1).lt.0.d0).or.(ql(1,i) .lt. 0.d0)) then
            write(*,*) 'Negative input: hl,hr,i=',qr(1,i-1),ql(1,i),i
         endif


c        !set normal direction
         if (ixy.eq.1) then
            mu=2
            nv=3
         else
            mu=3
            nv=2
         endif

         !zero (small) negative values if they exist
         if (qr(1,i-1).lt.0.d0) then
               qr(1,i-1)=0.d0
               qr(2,i-1)=0.d0
               qr(3,i-1)=0.d0
         endif

         if (ql(1,i).lt.0.d0) then
               ql(1,i)=0.d0
               ql(2,i)=0.d0
               ql(3,i)=0.d0
         endif

         !skip problem if in a completely dry area
         if (qr(1,i-1) <= drytol .and. ql(1,i) <= drytol) then
            go to 30
         endif

         !Riemann problem variables
         hL = qr(1,i-1)
         hR = ql(1,i)
         huL = qr(mu,i-1)
         huR = ql(mu,i)
         bL = auxr(1,i-1)
         bR = auxl(1,i)
         if (pressure_forcing) then
             pL = auxr(pressure_index, i-1)
             pR = auxl(pressure_index, i)
         end if

         hvL=qr(nv,i-1)
         hvR=ql(nv,i)

         !check for wet/dry boundary
         if (hR.gt.drytol) then
            uR=huR/hR
            vR=hvR/hR
            phiR = 0.5d0*g*hR**2 + huR**2/hR
         else
            hR = 0.d0
            huR = 0.d0
            hvR = 0.d0
            uR = 0.d0
            vR = 0.d0
            phiR = 0.d0
         endif

         if (hL.gt.drytol) then
            uL=huL/hL
            vL=hvL/hL
            phiL = 0.5d0*g*hL**2 + huL**2/hL
         else
            hL=0.d0
            huL=0.d0
            hvL=0.d0
            uL=0.d0
            vL=0.d0
            phiL = 0.d0
         endif

         wall(1) = 1.d0
         wall(2) = 1.d0
         wall(3) = 1.d0

c        ---- D-Claw yield check at wet/dry interface ----
c        When the wet cell is EXACTLY at rest (u=v=0, produced by the
c        floor-at-zero in src2.f90) and the free-surface head above the
c        dry bed is below the static Coulomb threshold, suppress inundation
c        (go to 30 = zero flux at this interface).
c        This prevents the deposit edge from spreading cell by cell into
c        adjacent dry terrain via the dam-break Riemann solution.
         if (imodel_rp .ge. 1) then
            if (ixy .eq. 1) then
               dx_n = dx_avac
            else
               dx_n = dy_avac
            endif
c           Right cell dry, left cell wet and exactly at rest
            if (hR .le. drytol .and. hL .gt. drytol .and.
     &          dsqrt(uL**2 + vL**2) .eq. 0.d0) then
               dh_n     = max(0.d0, hL + bL - bR)
               db_n     = dabs(bR - bL)
               costh_n  = dx_n / dsqrt(dx_n**2 + db_n**2)
c              Threshold uses mu*dx (not mu*cos(theta)*dx) to match the
c              physical Coulomb condition tan(theta) > mu.  The SW equations
c              overestimate the driving force by 1/cos(theta) relative to
c              the true slope-parallel gravity component g*h*sin(theta);
c              removing costh_n compensates for this approximation.
               thresh_n = mu_rp * dx_n
               if (dh_n .le. thresh_n) go to 30
            endif
c           Left cell dry, right cell wet and exactly at rest
            if (hL .le. drytol .and. hR .gt. drytol .and.
     &          dsqrt(uR**2 + vR**2) .eq. 0.d0) then
               dh_n     = max(0.d0, hR + bR - bL)
               db_n     = dabs(bR - bL)
               costh_n  = dx_n / dsqrt(dx_n**2 + db_n**2)
               thresh_n = mu_rp * dx_n
               if (dh_n .le. thresh_n) go to 30
            endif
         endif
c        ---- end wet/dry yield check ----

         if (hR.le.drytol) then
            call riemanntype(hL,hL,uL,-uL,hstar,s1m,s2m,
     &                                  rare1,rare2,1,drytol,g)
            hstartest=max(hL,hstar)
            if (hstartest+bL.lt.bR) then
c                bR=hstartest+bL
               wall(2)=0.d0
               wall(3)=0.d0
               hR=hL
               huR=-huL
               bR=bL
               phiR=phiL
               uR=-uL
               vR=vL
            elseif (hL+bL.lt.bR) then
               bR=hL+bL
            endif
         elseif (hL.le.drytol) then
            call riemanntype(hR,hR,-uR,uR,hstar,s1m,s2m,
     &                                  rare1,rare2,1,drytol,g)
            hstartest=max(hR,hstar)
            if (hstartest+bR.lt.bL) then
c               bL=hstartest+bR
               wall(1)=0.d0
               wall(2)=0.d0
               hL=hR
               huL=-huR
               bL=bR
               phiL=phiR
               uL=-uR
               vL=vR
            elseif (hR+bR.lt.bL) then
               bL=hR+bR
            endif
         endif

c        ---- D-Claw static yield check (George & Iverson 2014) ----
c
c        Applied when both cells are wet and EXACTLY at rest (u=v=0).
c        Cells are brought to exact zero by the floor-at-zero in src2.f90:
c          vnorm_new = max(0.d0, vnorm - dt*tau/rhoh)
c        so no velocity threshold (u_cr) is needed here.
c
c        The FREE-SURFACE gradient |d(h+b)/dn| is compared with the
c        static Coulomb yield threshold mu*cos(theta)*dx.
c        If the gradient is below the threshold, the free surface is
c        EQUALISED (hL+bL = hR+bR = eta_avg), which exactly triggers the
c        C-property of the augmented Riemann solver (George 2008):
c        quiescent fluid on any bed slope gives zero waves.
c        Simply equalising h would leave hL+bL != hR+bR on a sloped bed
c        and therefore drive spurious oscillations in the depth field.
         spd_L = dsqrt(uL**2 + vL**2)
         spd_R = dsqrt(uR**2 + vR**2)

         if (imodel_rp .ge. 1 .and.
     &       hL .gt. drytol .and. hR .gt. drytol .and.
     &       spd_L .eq. 0.d0 .and. spd_R .eq. 0.d0) then

c           Free-surface difference (full driving force d(h+b)/dn)
            dh_n   = dabs((hR + bR) - (hL + bL))
            db_n   = dabs(bR - bL)
            if (ixy .eq. 1) then
               dx_n = dx_avac
            else
               dx_n = dy_avac
            endif
c           cos(theta) at this interface: dx / sqrt(dx^2 + db^2)
            costh_n  = dx_n / dsqrt(dx_n**2 + db_n**2)
            h_avg_n  = 0.5d0 * (hL + hR)
c           Threshold uses mu*dx (not mu*cos(theta)*dx) to match the
c           physical Coulomb condition tan(theta) > mu.  The SW equations
c           overestimate the driving force by 1/cos(theta) relative to
c           the true slope-parallel gravity component g*h*sin(theta);
c           removing costh_n compensates for this approximation.
            thresh_n = mu_rp * dx_n
c           Cohesive Voellmy: cohesion raises the static threshold
            if (imodel_rp .eq. 3) then
               thresh_n = thresh_n
     &                  + C_rp / (rho_rp * g) * dx_n / h_avg_n
            endif
c           If free-surface gradient is below threshold:
c           equalise FREE SURFACE -> C-property -> zero waves
            if (dh_n .le. thresh_n) then
               eta_avg_n = 0.5d0 * ((hL + bL) + (hR + bR))
               hL_new    = eta_avg_n - bL
               hR_new    = eta_avg_n - bR
               if (hL_new .ge. 0.d0 .and. hR_new .ge. 0.d0) then
                  hL   = hL_new
                  hR   = hR_new
                  phiL = 0.5d0 * g * hL**2
                  phiR = 0.5d0 * g * hR**2
               endif
            endif
         endif
c        ---- end D-Claw static yield check ----

         !determine wave speeds
         sL=uL-sqrt(g*hL) ! 1 wave speed of left state
         sR=uR+sqrt(g*hR) ! 2 wave speed of right state

         uhat=(sqrt(g*hL)*uL + sqrt(g*hR)*uR)/(sqrt(g*hR)+sqrt(g*hL)) ! Roe average
         chat=sqrt(g*0.5d0*(hR+hL)) ! Roe average
         sRoe1=uhat-chat ! Roe wave speed 1 wave
         sRoe2=uhat+chat ! Roe wave speed 2 wave

         sE1 = min(sL,sRoe1) ! Eindfeldt speed 1 wave
         sE2 = max(sR,sRoe2) ! Eindfeldt speed 2 wave

         !--------------------end initializing...finally----------
         !solve Riemann problem.

         maxiter = 1

         call riemann_aug_JCP(maxiter,meqn,mwaves,hL,hR,huL,
     &        huR,hvL,hvR,bL,bR,uL,uR,vL,vR,phiL,phiR,pL,pR,sE1,sE2,
     &                                    drytol,g,rho,sw,fw)

c        !eliminate ghost fluxes for wall
         do mw=1,3
            sw(mw)=sw(mw)*wall(mw)

               fw(1,mw)=fw(1,mw)*wall(mw)
               fw(2,mw)=fw(2,mw)*wall(mw)
               fw(3,mw)=fw(3,mw)*wall(mw)
         enddo

         do mw=1,mwaves
            s(mw,i)=sw(mw)
            fwave(1,mw,i)=fw(1,mw)
            fwave(mu,mw,i)=fw(2,mw)
            fwave(nv,mw,i)=fw(3,mw)
         enddo

 30      continue
      enddo


c==========Capacity for mapping from latitude longitude to physical space====
        if (mcapa.gt.0) then
         do i=2-mbc,mx+mbc
          if (ixy.eq.1) then
             dxdc=(earth_radius*deg2rad)
          else
             dxdc=earth_radius*cos(auxl(3,i))*deg2rad
          endif

          do mw=1,mwaves
               s(mw,i)=dxdc*s(mw,i)
               fwave(1,mw,i)=dxdc*fwave(1,mw,i)
               fwave(2,mw,i)=dxdc*fwave(2,mw,i)
               fwave(3,mw,i)=dxdc*fwave(3,mw,i)
          enddo
         enddo
        endif

c===============================================================================


c============= compute fluctuations=============================================

         do i=2-mbc,mx+mbc
            do  mw=1,mwaves
               if (s(mw,i) < -1.d-14) then
                     amdq(1:3,i) = amdq(1:3,i) + fwave(1:3,mw,i)
               else if (s(mw,i) > 1.d-14) then
                  apdq(1:3,i)  = apdq(1:3,i) + fwave(1:3,mw,i)
               else
                 amdq(1:3,i) = amdq(1:3,i) + 0.5d0 * fwave(1:3,mw,i)
                 apdq(1:3,i) = apdq(1:3,i) + 0.5d0 * fwave(1:3,mw,i)
               endif
            enddo
         enddo

      return
      end subroutine
