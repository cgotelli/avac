! src2.f90 for AVAC 4: version = 2.0
subroutine src2(meqn,mbc,mx,my,xlower,ylower,dx,dy,q,maux,aux,t,dt)

    ! Called to update q by solving source term equation
    ! $q_t = \psi(q)$ over time dt starting at time t.
    !
    ! Explicit stopping treatment of the basal friction source term.
    ! Supported constitutive laws (selected via imodel in common /rheology/):
    !
    !   imodel = 1  Coulomb:          tau = mu * rho * g * h * cos(theta)
    !   imodel = 2  Voellmy:          tau = mu * rho * g * h * cos(theta)
    !                                     + rho * g / xi * speed^2
    !   imodel = 3  Cohesive Voellmy: tau = C + mu * rho * g * h * cos(theta)
    !                                     + rho * g / xi * speed^2
    !
    ! where speed = sqrt(u^2 + v^2) and theta is the local bed slope angle
    ! computed from the topography gradient (aux(1,:,:)).
    !
    ! Explicit update with floor at zero (after D-Claw, George & Iverson 2014):
    !   speed_new = max(0, speed - dt * tau / (rho * h))
    !   (hu)^{n+1} = (hu / speed) * h * speed_new
    !   (hv)^{n+1} = (hv / speed) * h * speed_new
    !
    ! This allows exact stopping (speed = 0 precisely).

    use geoclaw_module, only: g => grav, dry_tolerance
    use geoclaw_module, only: friction_forcing, friction_depth
    use rheology_module

    implicit none

    ! Rheological parameters (set by setprob.f90)
    double precision :: rho, mu, xi, C, u_cr
    integer :: imodel
    common /rheology/ rho, mu, xi, C, u_cr, imodel

    ! Input parameters
    integer, intent(in) :: meqn, mbc, mx, my, maux
    double precision, intent(in) :: xlower, ylower, dx, dy, t, dt

    ! Solution arrays
    double precision, intent(inout) :: q(meqn,1-mbc:mx+mbc,1-mbc:my+mbc)
    double precision, intent(inout) :: aux(maux,1-mbc:mx+mbc,1-mbc:my+mbc)

    ! Locals
    integer :: i, j
    real(kind=8) :: h, hu, hv, u, v, speed, speed_new, tau_rho
    real(kind=8) :: dzdx, dzdy, theta_local
    real(kind=8) :: tau_driving_rho, tau_static_rho
    logical :: at_rest

    if (friction_forcing) then
        do j = 1, my
            do i = 1, mx
                h = q(1,i,j)

                if (h <= dry_tolerance) then
                    q(2,i,j) = 0.d0
                    q(3,i,j) = 0.d0

                else if (h <= friction_depth) then
                    hu = q(2,i,j)
                    hv = q(3,i,j)

                    ! Local bed slope angle from centred topography gradient
                    dzdx = (aux(1,i+1,j) - aux(1,i-1,j)) / (2.d0*dx)
                    dzdy = (aux(1,i,j+1) - aux(1,i,j-1)) / (2.d0*dy)
                    theta_local = datan(dsqrt(dzdx**2 + dzdy**2))

                    ! Current speed
                    u = hu / h
                    v = hv / h
                    speed = dsqrt(u**2 + v**2)

                    ! Static yield test (Mohr-Coulomb): keep cells at rest if their
                    ! momentum is exactly zero and the driving stress is below yield.
                    ! A cell in motion must NOT be stopped here — it decelerates via
                    ! kinetic friction until speed_new reaches zero (see below).
                    !   tau_driving / rho = g * h * sin(theta)
                    !   tau_static  / rho = [C/rho +] mu * g * h * cos(theta)
                    ! (turbulent Voellmy term vanishes at v=0 => same for imodel=2)
                    tau_driving_rho = g * h * dsin(theta_local)
                    if (imodel == 3) then
                        tau_static_rho = C/rho + mu * g * h * dcos(theta_local)
                    else
                        tau_static_rho = mu * g * h * dcos(theta_local)
                    end if
                    at_rest = (speed == 0.d0) .and. (tau_driving_rho <= tau_static_rho)
                    if (at_rest) then
                        q(2,i,j) = 0.d0
                        q(3,i,j) = 0.d0
                    end if

                    if (.not. at_rest .and. speed > 0.d0) then
                        ! Kinematic friction stress tau/rho [m^2/s^2]
                        if (imodel == 1) then
                            tau_rho = coulomb_tau(mu, g, h, theta_local)
                        else if (imodel == 2) then
                            tau_rho = voellmy_tau(mu, g, h, theta_local, xi, speed)
                        else
                            tau_rho = cohesive_voellmy_tau(mu, g, h, theta_local, &
                                                           xi, speed, C, rho)
                        end if

                        ! Explicit update with floor at zero: exact stopping possible.
                        ! Mohr-Coulomb stop: if kinetic friction brings speed to zero
                        ! (speed_new <= 0) AND the driving stress is below yield,
                        ! the cell stops definitively.  A cell on a super-yield slope
                        ! (tau_driving > tau_static) must NOT be zeroed, otherwise
                        ! the slope re-accelerates it on the next step, creating a
                        ! freeze/restart oscillation that violates the CFL.
                        speed_new = speed - dt * tau_rho / h
                        if (speed_new <= 0.d0 .and. &
                            tau_driving_rho <= tau_static_rho) then
                            ! Definitive stop: slope cannot restart the cell.
                            q(2,i,j) = 0.d0
                            q(3,i,j) = 0.d0
                        else
                            ! Floor at zero, but no forced stop on super-yield slopes.
                            speed_new = max(0.d0, speed_new)
                            if (speed_new > 0.d0) then
                                q(2,i,j) = hu * speed_new / speed
                                q(3,i,j) = hv * speed_new / speed
                            else
                                q(2,i,j) = 0.d0
                                q(3,i,j) = 0.d0
                            end if
                        end if
                    end if
                end if
            end do
        end do
    end if

end subroutine src2
